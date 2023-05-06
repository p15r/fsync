#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import Enum
from ftplib import FTP  # nosec
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union


CONFIG_FILE = './config.json'
LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
RECURSION_LIMIT = 200


logging.basicConfig(level=LOGLEVEL, format='%(message)s')
sys.setrecursionlimit(RECURSION_LIMIT)


@dataclass
class Config:
    source_directory: str
    target_ip_address: str
    target_directory: str


class PathType(Enum):
    file = 'file'
    directory = 'directory'


# `order=True` & `compare=True` generate magic functions
# fsync requires `__lt__` magic function to compute delta using FSyncPaths
# (operation to compute delta: target dir - source dir)
@dataclass(order=True)
class FSyncPath:
    path_type: PathType = field(compare=False)

    # relative path
    rel_path: str = field(compare=True)

    # absolute path
    abs_path: str = field(compare=False)

    # file size (bytes)
    size: int = field(compare=True)

    def __hash__(self):
        return hash(self.rel_path)


def _usage() -> Tuple[str, str, str]:
    parser = argparse.ArgumentParser(
        description=(
            'Syncs local files to target (FTP server). Local is master '
            '(local changes are mirrored). '
            'Parameters are optional and overwrite settings from `config.yml`.'
        ),
        epilog='Source: https://github.com/p15r/fsync'
    )

    parser.add_argument(
        '--source-dir',
        required=False,
        help='source directory to sync'
    )
    parser.add_argument(
        '--target',
        required=False,
        help='sync target IP address'
    )
    parser.add_argument(
        '--target-dir',
        required=False,
        help='path to target directory'
    )

    args = parser.parse_args()

    return args.source_dir, args.target, args.target_dir


def bytes_to_mbytes(b: float) -> float:
    size = b / (1 << 20)
    size_r = round(size, 2)
    return size_r


def _load_config() -> Config:
    with open(CONFIG_FILE, 'r') as f_handle:
        cnt = json.load(f_handle)

    # `**cnt` unpacks dict into list of args for dataclass
    config = Config(**cnt)

    return config


def _login(target: str) -> FTP:
    ftp_session = FTP(target)   # nosec
    ftp_session.encoding = 'utf-8'
    ftp_session.login()
    ftp_session.sendcmd('OPTS UTF8 ON')

    if LOGLEVEL == 'DEBUG':
        ftp_session.set_debuglevel(1)

    welcome = ftp_session.getwelcome()

    if welcome:
        logging.info(f'Greeting from target: {welcome}')

    return ftp_session


def _list_remote(
    config: Config,
    ftp_session: FTP,
    path: str = ''
) -> Dict[str, str]:
    target_paths: Dict = {}

    if not path:
        path = config.target_directory

    subdirs = []
    files = []
    for name, meta in ftp_session.mlsd(path=path):
        if meta['type'] == 'file':
            files.append(FSyncPath(PathType.file, name, '', int(meta['size'])))

        if meta['type'] == 'dir':
            subdirs.append(FSyncPath(PathType.directory, name, '', 4096))

        target_paths['files'] = files

    if len(subdirs) == 0:
        return target_paths

    for sd in subdirs:
        sd_rel_path = sd.rel_path
        if sd_rel_path not in target_paths:
            target_paths[sd_rel_path] = {}

        target_paths[sd_rel_path] = _list_remote(
            config,
            ftp_session,
            f'{path}/{sd_rel_path}',
        )

    return target_paths


def _list_source(source_directory: Path) -> List[FSyncPath]:
    files = []

    # `rglob()` does not follow symlinks
    # https://github.com/python/cpython/issues/77609
    for path in source_directory.rglob('*'):
        abs_path = path.resolve()

        if abs_path.is_dir():
            # empty dirs do not get synced to target system
            if not os.listdir(abs_path):
                continue

        rel_path = abs_path.relative_to(source_directory)
        size = Path(abs_path).stat().st_size

        if abs_path.is_dir():
            p = FSyncPath(
                PathType.directory,
                rel_path.as_posix(),
                abs_path.as_posix(),
                4096
            )
        else:
            if abs_path.stem.startswith('.'):
                # ignore hidden files
                continue

            p = FSyncPath(
                PathType.file,
                rel_path.as_posix(),
                abs_path.as_posix(),
                int(size)
            )

        files.append(p)

    return files


def _to_list(
    config: Config,
    target_paths: Dict[str, str],
    path: str = ''
) -> List[FSyncPath]:
    """
    Converts the target directories dict into a list of FSyncPaths.
    """

    target_paths_converted: List[FSyncPath] = []

    if path == config.target_directory:
        path = ''

    for k, v in target_paths.items():
        if len(target_paths) == 1 and len(v) == 0:
            return target_paths_converted

        # keys of value `files` store file names, but are not part of paths,
        # hence ignore
        if k != 'files':
            if not path:
                path = k
            else:
                path = f'{path}/{k}'

        if isinstance(v, list):
            for item in v:
                if path == '':
                    # do not prefix files w/ path if in root
                    p = item.rel_path
                else:
                    p = f'{path}/{item.rel_path}'

                item.rel_path = p
                target_paths_converted.append(item)

        if isinstance(v, dict):
            if path:
                target_paths_converted.append(
                    FSyncPath(PathType.directory, path, '', 4096)
                )

            target_paths_converted.extend(_to_list(config, v, path))

            # all files of current directory processed, go to parent directory
            path = str(Path(path).parent)
            if path == '.':
                path = ''

    return target_paths_converted


def _calculate_delta(
    source_paths: List[FSyncPath],
    target_paths: List[FSyncPath]
) -> Tuple[List[FSyncPath], List[FSyncPath]]:
    to_add = set(source_paths) - set(target_paths)
    to_delete = set(target_paths) - set(source_paths)

    add = sorted(to_add)
    delete = sorted(to_delete)

    logging.info('Files to sync to target:')
    if len(add) == 0:
        logging.info('! Nothing to sync')
    else:
        for p in add:
            if len(p.rel_path) > 77:
                msg = (
                    f'+ ...{p.rel_path[len(p.rel_path)-77:]} '
                    f'({bytes_to_mbytes(p.size)} MB)'
                )
            else:
                msg = f'+ {p.rel_path} ({bytes_to_mbytes(p.size)} MB)'
            logging.info(msg)

    logging.info('Files/directories to remove on target:')
    if len(delete) == 0:
        logging.info('! Nothing to remove')
    else:
        for p in delete:
            if len(p.rel_path) > 77:
                msg = (
                    f'- ...{p.rel_path[len(p.rel_path)-77:]} '
                    f'({bytes_to_mbytes(p.size)} MB)'
                )
            else:
                msg = f'- {p.rel_path} ({bytes_to_mbytes(p.size)} MB)'
            logging.info(msg)

        input('Continue?')

    return add, delete


def _sync_delete(
    config: Config,
    ftp_session: FTP,
    paths: List[FSyncPath]
) -> bool:
    logging.info('Removing files/directories from target...')

    # sort by path length, so that files come first and
    # can be deleted before the directories that contain the files
    paths = sorted(paths, key=lambda s: len(s.rel_path), reverse=True)

    for path in paths:
        abs_path = f'{config.target_directory}/{path.rel_path}'

        try:
            if len(abs_path) > 77:
                msg = f'Deleting ...{abs_path[len(abs_path)-77:]}...'
            else:
                msg = f'Deleting {abs_path}...'

            logging.info(msg)

            if path.path_type == PathType.file:
                ftp_session.delete(abs_path)

            if path.path_type == PathType.directory:
                ftp_session.rmd(abs_path)
        except Exception as e:
            logging.error(f'Failed to remove {abs_path}: {e}')
            return False

    return True


def _sync_add_dir(config: Config, ftp_session: FTP, path: FSyncPath) -> bool:
    parent = str(Path(path.rel_path).parent)
    parents = parent.split('/')

    if parents == ['.']:
        # we're in root dir, no need to create
        return True

    abs_path = f'{config.target_directory}'
    for parent in parents:
        abs_path = f'{abs_path}/{parent}'
        logging.debug(f'Creating dir "{abs_path}"')
        res_path = ftp_session.mkd(abs_path)

        if not res_path:
            logging.error(f'Failed to create directory {res_path}')
            return False

    return True


def _sync_add(
    config: Config,
    ftp_session: FTP,
    source_directory: str,
    paths: List[FSyncPath]
) -> Union[float, bool]:
    logging.info('Syncing to target...')
    bytes_transferred: float = 0.0

    for item in paths:
        path = f'{source_directory}/{item.rel_path}'

        if Path(path).is_dir():
            continue

        if not _sync_add_dir(config, ftp_session, item):
            logging.error('Failed to create directories on target.')
            return False

        size = float(Path(path).stat().st_size)
        size_r = bytes_to_mbytes(size)

        if size == 0:
            # account for empty file
            size = 0.001

        with open(path, 'rb') as f_handle:
            if len(item.rel_path) > 77:
                msg = (
                    f'Uploading ...{item.rel_path[len(item.rel_path)-77:]} '
                    f'({size_r} MB)...'
                )
            else:
                msg = f'Uploading {item.rel_path} ({size_r} MB)...'
            logging.info(msg)
            try:
                ftp_session.storbinary(
                    f'STOR {config.target_directory}/{item.rel_path}',
                    f_handle
                )
            except Exception as e:
                logging.error(f'Failed to upload {item.rel_path}: {e}')
                return False

        bytes_transferred += size

    return bytes_transferred


def main() -> int:
    config = _load_config()
    param_source_directory, param_target, param_target_directory = _usage()

    if param_source_directory:
        config.source_directory = param_source_directory

    if param_target:
        config.target_ip_address = param_target

    if param_target_directory:
        config.target_directory = param_target_directory

    start_sync = datetime.now()

    source_paths = _list_source(Path(config.source_directory))

    if len(source_paths) == 0:
        input(
            'Source (local) directory is empty. '
            'Delete everything on target?'
        )

    logging.info('Authenticating...')
    ftp_session = _login(config.target_ip_address)

    logging.info('Getting target directory content...')
    target_paths = _list_remote(config, ftp_session)
    logging.debug(f'Files in target media directory: {target_paths}')

    if not target_paths:
        logging.info('No files found on target...')

    target_paths_converted = []
    target_paths_converted = _to_list(config, target_paths)

    add, remove = _calculate_delta(source_paths, target_paths_converted)

    if remove:
        if not _sync_delete(config, ftp_session, remove):
            logging.error('Failed to remove files on target.')
            return 1

    bytes_transferred: float = 0.0
    if add:
        bytes_transferred = _sync_add(
            config,
            ftp_session,
            config.source_directory,
            add
        )

        if not bytes_transferred:
            logging.error('Failed to sync source directory to target')
            return 1

    ftp_session.quit()

    end_sync = datetime.now()
    duration = end_sync - start_sync
    logging.info(
        f'Sync took {duration} ({bytes_to_mbytes(bytes_transferred)} '
        'MB transferred)'
    )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
