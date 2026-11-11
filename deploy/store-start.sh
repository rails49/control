#!/bin/sh
#
# The store's start: a name for whatever uid the store runs as, then the
# command it is given (`deploy/compose.yaml` runs `tc49 serve` through this).
#
# OpenSSH and `ssh-keygen` refuse a uid with no passwd entry, and the backup
# makes its key and pushes with them. The uid is the box's, set at run time,
# so one image serves every box. `nss_wrapper` answers the lookups from a
# one-line passwd and group file written here under `/tmp`, and `/etc/passwd`
# and `/etc/group` stay root's (#1216, rails49/.github#71 decision 3).
#
# `/tmp` is the home in the entry, as `HOME` is in compose: ssh writes its
# `~/.ssh` there and nothing is kept in it.
set -eu

printf 'tc49:x:%s:%s:tc49:/tmp:/usr/sbin/nologin\n' "$(id -u)" "$(id -g)" >/tmp/passwd
printf 'tc49:x:%s:\n' "$(id -g)" >/tmp/group

LD_PRELOAD=libnss_wrapper.so
NSS_WRAPPER_PASSWD=/tmp/passwd
NSS_WRAPPER_GROUP=/tmp/group
export LD_PRELOAD NSS_WRAPPER_PASSWD NSS_WRAPPER_GROUP

exec "$@"
