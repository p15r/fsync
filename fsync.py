#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from ftplib import FTP  # nosec
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union

import yaml


CONFIG_FILE = './config.yml'
LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
RECURSION_LIMIT = 100

# a path marker is appended to a path to track it's type (d: dir, f: file)
# e.g. '/var/lib/test###f', '/var/log/http###d'
PATH_MARKER = '###'


# TODO:
# - transfer folder and file names with dots in it
# - create abstract data model for both target &  local lib:
#   [
#       {
#           'type': 'dir',
#           'rel_p': 'xmas/santa.mp3',
#           'abs_path': '/home/pat/xmas/santa.mp3'
#       }
#   ]
#   make this a dataclass

logging.basicConfig(level=LOGLEVEL, format='%(message)s')
sys.setrecursionlimit(RECURSION_LIMIT)


@dataclass
class Config:
    local_music_library: str
    target_ip_address: str
    target_music_lib_root_dir: str


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
        '--lib',
        required=False,
        help='path to local music library'
    )
    parser.add_argument(
        '--target',
        required=False,
        help='sync target IP address'
    )
    parser.add_argument(
        '--target-lib',
        required=False,
        help='path to music library on target'
    )

    args = parser.parse_args()

    return args.lib, args.target, args.target_lib


def _load_config() -> Config:
    with open(CONFIG_FILE, 'r') as f_handle:
        cnt = yaml.safe_load(f_handle)

    # `**cnt` unpacks dict into list of args for dataclass
    config = Config(**cnt)

    return config


def _login(target: str) -> FTP:
    ftp = FTP(target)   # nosec
    ftp.encoding = 'utf-8'
    ftp.login()
    ftp.sendcmd('OPTS UTF8 ON')

    welcome = ftp.getwelcome()

    if welcome:
        logging.info(f'Greeting from target: {welcome}')

    return ftp


def _list_remote(config: Config, ftp: FTP, path: str = '',) -> Dict[str, str]:
    target_db: Dict = {}

    if not path:
        path = config.target_music_lib_root_dir

    subdirs = []
    files = []
    for name, meta in ftp.mlsd(path=path):
        if meta['type'] == 'file':
            files.append(name)

        if meta['type'] == 'dir':
            subdirs.append(name)

        target_db['files'] = files

    if len(subdirs) == 0:
        return target_db

    for sd in subdirs:
        if sd not in target_db:
            target_db[sd] = {}

        target_db[sd] = _list_remote(
            config,
            ftp,
            f'{path}/{sd}',
        )

    return target_db


def _list_local(music_lib: Path) -> List[Path]:
    files = []

    for path in music_lib.rglob('*'):
        abs_path = path.resolve()

        if abs_path.is_dir():
            # empty folders do not get synced to target system
            if not os.listdir(abs_path):
                continue

        rel_path = abs_path.relative_to(music_lib)
        files.append(rel_path)

    return files


def _to_list(config: Config, lib: Dict[str, str], path: str = '') -> List[str]:
    """
    Converts the lib dict into a list that contains all directories and
    files of the target system.
    """

    lib_converted: List[str] = []

    if path == config.target_music_lib_root_dir:
        path = ''

    for k, v in lib.items():
        if len(lib) == 1 and len(v) == 0:
            return lib_converted

        # keys of value `files` store file names, but are not part of paths,
        # hence ignored
        if k != 'files':
            if not path:
                path = k
            else:
                path = f'{path}/{k}'

        if isinstance(v, list):
            for item in v:
                if path == '':
                    # do not prefix files w/ path if in root
                    p = item
                else:
                    p = f'{path}/{item}'

                lib_converted.append(f'{p}{PATH_MARKER}f')

        if isinstance(v, dict):
            if path:
                lib_converted.append(f'{path}{PATH_MARKER}d')

            lib_converted.extend(_to_list(config, v, path))

            # all files of current directory added, go to parent directory
            path = str(Path(path).parent)
            if path == '.':
                path = ''

    return lib_converted


def _calculate_delta(
    local_lib: List[Path],
    target_lib: List[str]
) -> Tuple[List[str], List[str]]:
    # convert list of Path objects to list of strings
    local_lib_str = [p.as_posix() for p in local_lib]

    # remove PATH_MARKERs
    target_lib_no_marker = [p.split(PATH_MARKER)[0] for p in target_lib]

    to_add = set(local_lib_str) - set(target_lib_no_marker)
    to_delete = set(target_lib_no_marker) - set(local_lib_str)

    # sort by path length, so that files come first and
    # can be deleted before the directories that contain the files
    add = sorted(to_add)
    delete = sorted(to_delete)

    logging.info('Files to sync to target:')
    if len(add) == 0:
        logging.info('! Nothing to sync')
    else:
        for p in add:
            if len(p) > 77:
                msg = f'+ ...{p[len(p)-77:]}'
            else:
                msg = f'+ {p}'
            logging.info(msg)

    logging.info('Files/folders to remove on target:')
    if len(delete) == 0:
        logging.info('! Nothing to remove')
    else:
        for p in delete:
            if len(p) > 77:
                msg = f'- ...{p[len(p)-77:]}'
            else:
                msg = f'- {p}'
            logging.info(msg)

        input('Continue?')

    # add back PATH_MARKER
    add_back = []
    for path in delete:
        for orig_path in target_lib:
            if f'{path}{PATH_MARKER}f' == orig_path:
                add_back.append((path, orig_path))
            if f'{path}{PATH_MARKER}d' == orig_path:
                add_back.append((path, orig_path))

    for item in add_back:
        delete.remove(item[0])
        delete.append(item[1])

    return add, delete


def _sync_delete(config: Config, ftp: FTP, lib: List[str]) -> bool:
    logging.info('Removing files/folders from target...')

    lib = sorted(lib, key=lambda s: len(s), reverse=True)

    for path in lib:
        path, path_type = path.split(PATH_MARKER)
        path = f'{config.target_music_lib_root_dir}/{path}'

        try:
            if len(path) > 77:
                msg = f'Deleting ...{path[len(path)-77:]}...'
            else:
                msg = f'Deleting {path}...'

            logging.info(msg)

            if path_type == 'f':
                ftp.delete(path)

            if path_type == 'd':
                ftp.rmd(path)
        except Exception as e:
            logging.error(f'Failed to remove {path}: {e}')
            return False

    return True


def _sync_add_dir(config: Config, ftp: FTP, path: str) -> bool:
    parent = str(Path(path).parent)
    parents = parent.split('/')

    if parents == ['.']:
        # we're in root dir, no need to create
        return True

    abs_path = f'{config.target_music_lib_root_dir}'
    for parent in parents:
        abs_path = f'{abs_path}/{parent}'
        logging.debug(f'Creating dir "{abs_path}"')
        res_path = ftp.mkd(abs_path)

        if not res_path:
            logging.error(f'Failed to create directory {res_path}')
            return False

    return True


def _sync_add(
    config: Config,
    ftp: FTP,
    source_lib: str,
    lib: List[str]
) -> Union[float, bool]:
    logging.info('Syncing to target...')
    mbytes_transferred: float = 0.0

    for item in lib:
        path = f'{source_lib}/{item}'

        if Path(path).is_dir():
            continue

        if not _sync_add_dir(config, ftp, item):
            logging.error('Failed to create directories on target.')
            return False

        size = Path(path).stat().st_size / (1 << 20)
        size_r = round(size, 2)
        with open(path, 'rb') as f_handle:
            if len(item) > 77:
                msg = f'Uploading ...{item[len(item)-77:]} ({size_r} MB)...'
            else:
                msg = f'Uploading {item} ({size_r} MB)...'
            logging.info(msg)
            try:
                ftp.storbinary(
                    f'STOR {config.target_music_lib_root_dir}/{item}',
                    f_handle
                )
            except Exception as e:
                logging.error(f'Failed to upload {item}: {e}')
                return False

        mbytes_transferred += size

    return mbytes_transferred


def main() -> int:
    config = _load_config()

    param_source_lib, param_target, param_target_lib = _usage()

    if param_source_lib:
        config.local_music_library = param_source_lib

    if param_target:
        config.target_ip_address = param_target

    if param_target_lib:
        config.target_music_lib_root_dir = param_target_lib

    start_sync = datetime.now()

    local_lib = _list_local(Path(config.local_music_library))

    if len(local_lib) == 0:
        input('Local library is empty. Delete everything on target?')

    logging.info('Authenticating...')
    ftp = _login(config.target_ip_address)

    logging.info('Get target library...')
    target_lib = _list_remote(config, ftp)
    logging.debug(f'Files in target media lib: {target_lib}')

    if not target_lib:
        logging.info('No files found on target...')

    target_lib_converted = []
    target_lib_converted = _to_list(config, target_lib)

    add, remove = _calculate_delta(local_lib, target_lib_converted)

    if remove:
        if not _sync_delete(config, ftp, remove):
            logging.error('Failed to remove files on target.')
            return 1

    mbytes_transferred: float = 0.0
    if add:
        mbytes_transferred = _sync_add(
            config,
            ftp,
            config.local_music_library,
            add
        )

        if not mbytes_transferred:
            logging.error('Failed to sync local lib to target')
            return 1

    # TODO: rename ftp to ftp_session
    ftp.quit()

    end_sync = datetime.now()
    duration = end_sync - start_sync
    logging.info(
        f'Sync took {duration} ({round(mbytes_transferred, 2)} MB transferred)'
    )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
