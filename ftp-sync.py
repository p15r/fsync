#!/usr/bin/env python3

import argparse
from ftplib import FTP
from pathlib import Path
from typing import List


REMOTE_MUSIC_LIB_ROOT_DIR = 'foobar2000 Music Folder'


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
    ftp.login()

    welcome = ftp.getwelcome()

    if welcome:
        print(f'Target greeting: {welcome}')

    return ftp


def _list_remote(ftp: FTP, cwd=None, files=None) -> List[str]:
    # TODO: use default values instead of `if not files`

    if not files:
        files = {}

    if not cwd:
        cwd = REMOTE_MUSIC_LIB_ROOT_DIR
        files[cwd] = {}

    k_cwd = cwd.split('/')[-1]

    dr = []     # subdirs in current dir
    f = []      # files in current dir
    for name, meta in ftp.mlsd(path=cwd):
        if meta['type'] == 'file':
            f.append(name)

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
            files[k_cwd]
        )

    return files


def _list_local(music_lib: Path) -> List[str]:
    files = []

    for p in music_lib.rglob('*'):
        # TODO: instead of string casting, use p.resolve().as_uri() &
        #       parse target files also into URLs
        files.append(str(p.resolve()))

    return files


def _to_list(lib, path=None, local_list=None, final_lib=None) -> List[str]:
    # TODO: use default values instead of `if not local_list`

    if not final_lib:
        final_lib = []

    if not local_list:
        local_list = []

    if not path:
        path = ''

    for k, v in lib.items():
        if k != 'files':
            path = f'{path}/{k}'

        if isinstance(v, list):
            for item in v:
                local_list.append(f'{path}/{item}')
                return local_list

        if isinstance(v, dict):
            final_lib.extend(_to_list(v, path, local_list, final_lib))

    return final_lib


def main() -> int:
    source_lib, target = _usage()

    # print('Authenticating...')
    # ftp = _login(target)

    # print('List remote music library...')
    # current_target_library = _list_remote(ftp)

    current_local_library = _list_local(Path(source_lib))

    with open('mock_remote_lib.json', 'r') as f:
        import json
        current_target_library = json.load(f)

    current_target_library = _to_list(current_target_library)

    missing_on_target = set(current_local_library) - set(current_target_library)
    delete_on_target = set(current_target_library) - set(current_local_library)

    breakpoint()

    # TODO: terminate connection

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
