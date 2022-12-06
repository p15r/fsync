#!/usr/bin/env python3
import argparse
import logging
import os
import urllib.request as UL
from datetime import datetime
from ftplib import FTP
from pathlib import Path
from typing import List


# NO TRAILING SLASH
REMOTE_MUSIC_LIB_ROOT_DIR = 'foobar2000 Music Folder'

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(level=LOGLEVEL)



# TODO: make helpers: path2url & url2path


def _usage() -> str:
    parser = argparse.ArgumentParser(
        prog = 'FTP Sync',
        description = 'Syncs local files to remote. Local is master.',
        epilog = 'Source: https://github.com:p15r'
    )

    parser.add_argument('music_lib', help='path to local music library')
    parser.add_argument('target', help='sync target IP address')

    args = parser.parse_args()
    target = args.target

    source_lib = args.music_lib

    return source_lib, target


def _login(target: str) -> FTP:
    ftp = FTP(target)
    ftp.set_debuglevel(0)
    ftp.login()

    welcome = ftp.getwelcome()

    if welcome:
        logging.info(f'Target greeting: {welcome}')

    return ftp


def _path_encode(p):
    return UL.pathname2url(p)


def _list_remote(ftp: FTP, cwd=None, files={}) -> List[str]:
    if not cwd:
        cwd = REMOTE_MUSIC_LIB_ROOT_DIR
        files[cwd] = {}

    k_cwd = cwd.split('/')[-1]

    dr = []     # subdirs in current dir
    f = []      # files in current dir
    for name, meta in ftp.mlsd(path=cwd):
        if meta['type'] == 'file':
            f.append(_path_encode(name))

        if meta['type'] == 'dir':
            dr.append(name)

    files[k_cwd]['files'] = f

    if len(dr) == 0:
        return f

    for d in dr:
        files[k_cwd][d] = {}
        _list_remote(
            ftp,
            f'{cwd}/{d}',
            files[k_cwd],
        )

    return files


def _list_local(music_lib: Path) -> List[str]:
    files = []

    for p in music_lib.rglob('*'):
        # TODO: instead of string casting, use p.resolve().as_uri() &
        #       parse target files also into URLs
        absolute_path = p.resolve()
        relative_path = absolute_path.relative_to(music_lib)
        files.append(_path_encode(str(relative_path)))

    return files


def _to_list(lib, path='') -> List[str]:
    local_list = []

    if path == REMOTE_MUSIC_LIB_ROOT_DIR:
        path = ''

    for k, v in lib.items():
        if k != 'files':
            if not path:
                path = k
            else:
                path = f'{path}/{k}'

        if isinstance(v, list):
            for item in v:
                local_list.append(f'{path}/{item}')

        if len(lib) == 1 and len(v) == 0:
            return local_list

        if isinstance(v, dict):
            if path != REMOTE_MUSIC_LIB_ROOT_DIR:
                local_list.append(path)
            local_list.extend(_to_list(v, path))

            # we've done a directory, go back one directory
            path = str(Path(path).parent)
            if path == '.':
                path = ''

    return local_list


def _calculate_delta(local_lib, target_lib):
    to_add = set(local_lib) - set(target_lib)
    to_delete = set(target_lib) - set(local_lib)

    to_add = sorted(to_add)
    to_delete = sorted(to_delete)

    ## <remove folders>
    remove = set()
    for item in to_add:
        child = item.split('/')[-1]
        if len(child.split('.')) == 1:
            # TODO:
            # if a folder has a dot in it, it would not be removed and
            # thus synced to the target (solved when using Path instead of
            # strings; then we do not even add dirs to the lib.
            remove.add(item)

    for item in remove:
        to_add.remove(item)
    ## </remove folders>

    logging.info('Tracks to sync:')
    if len(to_add) == 0:
        logging.info('! Nothing to sync')
    else:
        [logging.info(f'+ {x}') for x in to_add]

    logging.info('Tracks to remove:')
    if len(to_delete) == 0:
        logging.info('! Nothing to remove')
    else:
        [logging.info(f'- {x}') for x in to_delete]
        input('Continue and remove files?')

    return to_add, to_delete


def _sync_delete(ftp, lib):
    logging.info('Removing files on target...')

    # TODO: my delta compute mechanism doesn't allow me to figure out if
    #       a folder has been removed, thus I need to iterate over all
    #       folders, check if they are empty, then delete them

    lib = sorted(lib, key=lambda s: len(s), reverse=True)

    for item in lib:
        item = UL.url2pathname(item)

        item = f'{REMOTE_MUSIC_LIB_ROOT_DIR}/{item}'

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


def _sync_add(ftp, source_lib, lib):
    for item in lib:
        item = UL.url2pathname(item)
        path = f'{source_lib}/{item}'

        # TODO: ensure lib is sorted - didn't I do this before??

        # <DIR>
        dir = str(Path(item).parent)
        dirs = dir.split('/')

        tmp = ''
        for d in dirs:
            if not tmp:
                tmp = f'{REMOTE_MUSIC_LIB_ROOT_DIR}/{d}'
            else:
                tmp = f'{tmp}/{d}'

            if tmp == REMOTE_MUSIC_LIB_ROOT_DIR:
                # TODO: can this be done more elegant?
                continue
            ftp.mkd(tmp)
        # </DIR>

        # TODO: print bytes transfered
        # TODO: stat: file x of total (progress percentage)
        with open(path, 'rb') as f_handle:
            logging.info(f'Uploading {item}...')
            # cwd?
            ftp.storbinary(
                f'STOR {REMOTE_MUSIC_LIB_ROOT_DIR}/{item}',
                f_handle
            )


def main() -> int:
    source_lib, target = _usage()

    start_sync = datetime.now()

    local_lib = _list_local(Path(source_lib))

    if len(local_lib) == 0:
        input('Local library is empty. Delete everything on target?')

    logging.info('Authenticating...')
    ftp = _login(target)

    logging.info('Get target music library...')
    target_lib = _list_remote(ftp)
    logging.debug(f'Files in target media lib: {target_lib}')

    empty_target = False
    # TODO: is this always a list?
    if isinstance(target_lib, list):
        logging.info('No files found on target...')
        empty_target = True

    if not empty_target:
        target_lib = _to_list(target_lib)
        logging.debug('_to_list() ended')

    add, remove = _calculate_delta(local_lib, target_lib)

    if not empty_target:
        logging.info('Removing files from target...')
        _sync_delete(ftp, remove)

    logging.info('Syncing files to target...')
    _sync_add(ftp, source_lib, add)

    # TODO: rename ftp to ftp_session
    ftp.quit()

    end_sync = datetime.now()
    duration = end_sync - start_sync
    logging.info(f'Sync took {duration}')

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
