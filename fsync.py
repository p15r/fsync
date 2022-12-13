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

import yaml


CONFIG_FILE = './config.yml'
LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
RECURSION_LIMIT = 100


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


def _list_local(music_lib: Path) -> List[str]:
    files = []

    for path in music_lib.rglob('*'):
        abs_path = path.resolve()
        rel_path = abs_path.relative_to(music_lib)
        files.append(rel_path.as_posix())

    return files


def _to_list(config: Config, lib: Dict[str, str], path: str = '') -> List[str]:
    local_list: List[str] = []

    if path == config.target_music_lib_root_dir:
        path = ''

    for k, v in lib.items():
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

                local_list.append(p)

        if len(lib) == 1 and len(v) == 0:
            return local_list

        if isinstance(v, dict):
            if path != config.target_music_lib_root_dir:
                local_list.append(path)
            local_list.extend(_to_list(config, v, path))

            # we've done a directory, go back one directory
            path = str(Path(path).parent)
            if path == '.':
                path = ''

    return local_list


def _calculate_delta(local_lib: List[str], target_lib: List[str]):
    to_add = set(local_lib) - set(target_lib)
    to_delete = set(target_lib) - set(local_lib)

    add = sorted(to_add)
    delete = sorted(to_delete)

    # <remove folders>
    remove = set()
    for item in add:
        child = item.split('/')[-1]
        if len(child.split('.')) == 1:
            # TODO:
            # if a folder has a dot in it, it would not be removed and
            # thus synced to the target (solved when using Path instead of
            # strings; then we do not even add dirs to the lib.
            remove.add(item)

    for item in remove:
        add.remove(item)
    # </remove folders>

    logging.info('Files to sync to target:')
    if len(add) == 0:
        logging.info('! Nothing to sync')
    else:
        for x in add:
            p = x
            if len(p) > 77:
                msg = f'+ ...{p[len(p)-77:]}'
            else:
                msg = f'+ {p}'
            logging.info(msg)

    logging.info('Files/folders to remove on target:')
    if len(delete) == 0:
        logging.info('! Nothing to remove')
    else:
        for x in delete:
            p = x
            if len(p) > 77:
                msg = f'- ...{p[len(p)-77:]}'
            else:
                msg = f'- {p}'
            logging.info(msg)
        input('Continue?')

    return add, delete


def _sync_delete(config: Config, ftp: FTP, lib: List[str]):
    logging.info('Removing files/folders from target...')

    # TODO: my delta compute mechanism doesn't allow me to figure out if
    #       a folder has been removed, thus I need to iterate over all
    #       folders, check if they are empty, then delete them

    lib = sorted(lib, key=lambda s: len(s), reverse=True)

    for item in lib:
        item = f'{config.target_music_lib_root_dir}/{item}'

        item_type = ''
        split = item.split('.')
        if len(split) == 1:
            item_type = 'directory'
        else:
            item_type = 'file'

        try:
            logging.debug(f'Delete {item_type} {item}')

            if item_type == 'file':
                ftp.delete(item)

            if item_type == 'directory':
                ftp.rmd(item)
        except Exception as e:
            logging.error(f'Failed to remove {item_type} {item}: {e}')


def _sync_add(
    config: Config,
    ftp: FTP,
    source_lib: str,
    lib: List[str]
) -> float:
    logging.info('Syncing to target...')
    mbytes_transferred: float = 0

    for item in lib:
        path = f'{source_lib}/{item}'

        # TODO: ensure lib is sorted - didn't I do this before??

        # <DIR>
        dir = str(Path(item).parent)
        dirs = dir.split('/')

        tmp = ''
        for d in dirs:
            if d == '.':
                # TODO: why do I get a dot? Can I remove it before I get here?
                continue

            if not tmp:
                tmp = f'{config.target_music_lib_root_dir}/{d}'
            else:
                tmp = f'{tmp}/{d}'

            if tmp == config.target_music_lib_root_dir:
                # TODO: can this be done more elegant?
                continue

            logging.debug(f'Creating dir "{tmp}"')
            ftp.mkd(tmp)
        # </DIR>

        # TODO: stat: file x of total (progress percentage)
        size = Path(path).stat().st_size / (1 << 20)
        size_r = round(size, 2)
        with open(path, 'rb') as f_handle:
            if len(item) > 77:
                msg = f'Uploading ...{item[len(item)-77:]} ({size_r} MB)...'
            else:
                msg = f'Uploading {item} ({size_r} MB)...'
            logging.info(msg)
            ftp.storbinary(
                f'STOR {config.target_music_lib_root_dir}/{item}',
                f_handle
            )

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

    # TODO: remove empty target once target_lib has been refactored
    #       and doesn't break _to_list() if empty
    empty_target = False
    if not target_lib:
        logging.info('No files found on target...')
        empty_target = True

    target_lib_converted = []
    if not empty_target:
        target_lib_converted = _to_list(config, target_lib)

    add, remove = _calculate_delta(local_lib, target_lib_converted)

    if remove:
        _sync_delete(config, ftp, remove)

    mbytes_transferred: float = 0.0
    if add:
        mbytes_transferred = _sync_add(
            config,
            ftp,
            config.local_music_library,
            add
        )

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
