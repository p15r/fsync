# Readme
`fsync` is a script that behaves like `rsync -a` over FTP.

The system that executes the script is the master instance, which means its
local files will be **mirrored** to the target system. If files have been
deleted locally on the master, they will also be deleted on the target. If
files exist on the target, but not on master, the files will be **deleted
on the target**.

This script actually uses plain FTP - no encryption support. This is insecure.

I created `fsync` to sync my music library from my computer to my mobile
device over a local network.
