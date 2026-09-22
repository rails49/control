#!/bin/sh
#
# Give this container's uid a name, then run what the service was asked to run.
#
# The store runs as the person who deployed the box — an arbitrary host uid,
# so that every drawing the editor saves is theirs on the host (#320, #387) —
# and the image knows nothing about that uid. OpenSSH refuses to run for a uid
# with no passwd entry, "No user exists for uid 501", and the backup makes its
# deploy key with `ssh-keygen` and pushes with `ssh`: on a box whose uid the
# tables do not name, the whole backup feature is unreachable (#566).
#
# **The name is the image's answer, not the box's.** The host's own `/etc/passwd`
# came in read-only before this, which answers the question only where the host
# keeps its people in that file. macOS keeps them in Open Directory, so a mac
# hands the store uid 501 and a passwd file that has never heard of it; a Linux
# box hands it whatever `id -u` says and the image has no entry for that either
# — it worked there only where the uid happened to be one the base image ships.
# What the uid is called is a question about the container, and the container
# answers it for whatever uid it is handed.
#
# Nothing here is a login: the entry exists so that a name lookup finds one.
# `/tmp` is its home, which is where `HOME` points too, because ssh reads the
# home out of the passwd entry rather than out of the environment and writes
# its `~/.ssh` there. Nothing is kept in it — the host keys are in the image
# and the deploy key is in the `keys` volume.
#
# The tables are the image's own copies, group-writable to root's group, and
# the one service that runs as somebody the image does not know is in that
# group (`compose.yaml`). A uid that is named already — root, which is every
# other service here — is left alone, and a container that cannot write them
# says so and goes on to run its command: the store then reports a backup it
# cannot make, which is the fault this is about, rather than refusing to come
# up at all.
#
# `TC49_ETC` is where the tables are. It is never set in the deployment; it is
# how `tests/system/test_the_uid_has_a_name.py` runs this script for real.

set -eu

NAME=tc49
ETC=${TC49_ETC:-/etc}
uid=$(id -u)
gid=$(id -g)

# Whether `$2` is already an id in `$1` — the third field of a passwd or a
# group line. The lookup is the file itself, which is all a slim image has.
listed() {
  cut -d: -f3 "$1" 2>/dev/null | grep -qx "$2"
}

# Append `$2` to `$1`, or say why the uid stays nameless.
append() {
  if [ -w "$1" ]; then
    printf '%s\n' "$2" >>"$1"
  else
    echo "entrypoint: $1 is not writable, so uid $uid has no name here:" \
      "anything that resolves the user rather than the id will fail (#566)" >&2
  fi
}

listed "$ETC/passwd" "$uid" ||
  append "$ETC/passwd" "$NAME:x:$uid:$gid:tc49:/tmp:/usr/sbin/nologin"
listed "$ETC/group" "$gid" ||
  append "$ETC/group" "$NAME:x:$gid:"

exec "$@"
