![gh action status][ghactiontesting]

# Readme
`fsync` is a script that behaves like `rsync -a` over FTP.

The system that executes the script is the master instance, which means its
local files will be **mirrored** to the target system. If files have been
deleted locally on the master, they will also be deleted on the target. If
files exist on the target, but not on master, the files will be **deleted
on the target**. Symlinks in source directory (on master) are ignored.

This script actually uses plain FTP - no encryption support. This is insecure.

I created `fsync` to sync my music library from my computer to my mobile
device over a local network.

[ghactiontesting]: https://github.com/p15r/fsync/actions/workflows/tests.yml/badge.svg
