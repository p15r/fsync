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


def _path_encode(p):
    from urllib.request import pathname2url
    return pathname2url(p)


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
            files[k_cwd]
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


def _to_list(lib, path='', final_lib=[]) -> List[str]:
    local_list = []

    # TODO: made default param
    if path == REMOTE_MUSIC_LIB_ROOT_DIR:
        # for music lib comparison, paths must be from lib root
        path = ''

    #breakpoint()
    for k, v in lib.items():
        if k != 'files':
            # TODO: doc why k != 'files'
            if len(path) == 0:
                path = k
            else:
                path = f'{path}/{k}'

        # TODO: this is true if 'files':[] in root is iterated,
        #       if I do not jump over it, the recursion stop. why?
        if k == 'files' and len(v) == 0: continue

        if isinstance(v, list):
            for item in v:
                local_list.append(f'{path}/{item}')
            return local_list

        if isinstance(v, dict):
            final_lib.extend(_to_list(v, path, final_lib))

            # we've done a directory, go back one directory
            path = str(Path(path).parent)
            if path == '.':
                path = ''

    return final_lib


def _calculate_delta(local_lib, target_lib):
    to_add = set(local_lib) - set(target_lib)
    to_delete = set(target_lib) - set(local_lib)

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

    print('### Tracks to sync:')
    [print(f'- {x}') for x in sorted(to_add)]

    print('\n### Tracks to delete:')
    [print(f'- {x}') for x in sorted(to_delete)]

    return to_add, to_delete


def main() -> int:
    source_lib, target = _usage()

    #print('Authenticating...')
    #ftp = _login(target)

    #print('List remote music library...')
    #target_lib = _list_remote(ftp)

    local_lib = _list_local(Path(source_lib))

    with open('mock_remote_lib.json', 'r') as f:
        import json
        target_lib = json.load(f)

    target_lib = _to_list(target_lib)

    add, remove = _calculate_delta(local_lib, target_lib)

    breakpoint()

    # TODO: terminate connection

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
