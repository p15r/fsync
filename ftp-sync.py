#!/usr/bin/env python3
import argparse
from ftplib import FTP
from typing import List


REMOTE_MUSIC_LIB_ROOT_DIR = 'foobar2000 Music Folder'


def _usage() -> str:
    parser = argparse.ArgumentParser(
        prog = 'FTP Sync',
        description = 'Syncs local files to remote. Local is master.',
        epilog = 'Source: https://github.com:p15r'
    )

    parser.add_argument('remote')

    args = parser.parse_args()
    remote = args.remote

    return remote


def _login(remote: str) -> FTP:
    ftp = FTP(remote)
    ftp.login()

    welcome = ftp.getwelcome()

    if welcome:
        print(f'Remote greeting: {welcome}')

    return ftp


def _list_remote(ftp: FTP, cwd=None, files=None) -> List[str]:
    if not files:
        files = {}

    if not cwd:
        cwd = REMOTE_MUSIC_LIB_ROOT_DIR
        files[cwd] = {}

    k_cwd = cwd.split('/')[-1]

    dr = []
    f = []
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


def main() -> int:
    remote = _usage()

    print('Authenticating...')
    ftp = _login(remote)

    print('List remote music library...')
    files = _list_remote(ftp)

    breakpoint()

    # TODO: terminate connection

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
