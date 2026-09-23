# The image names the store's uid at build

Records the decision behind [#570](https://github.com/rails49/control/issues/570),
which reviewed the fix for [#566](https://github.com/rails49/control/issues/566).

The store runs as the person who deployed the box, so that every file it
writes into their store directory is theirs on the host
([#320](https://github.com/rails49/control/issues/320),
[#387](https://github.com/rails49/control/issues/387)). Every other service
runs as root. The backup makes its deploy key with `ssh-keygen` and pushes with
`ssh`, and OpenSSH exits before it reads the environment when the uid has no
passwd entry: "No user exists for uid 501". So the uid needs a name inside the
container.

The host's own `/etc/passwd` came in read-only for this. That worked only where
the host keeps its users in that file, which a mac does not. #566 replaced it
with an entrypoint that appended an entry at startup. For that to work, the
image made `/etc/passwd` and `/etc/group` writable by root's group, and the
store joined root's group.

## What that cost

The tables stayed writable for the container's whole life, not just while the
entrypoint used them. The store process could add a line naming uid 0, and the
base image carries `su`. The store is the one service that is not root, and
that was deliberate: a store running as root writes root-owned files into the
person's directory, which is the fault #387 fixed. A store able to make itself
root undoes that. The entrypoint also wrapped all eight services for a fault
only the store has.

## Decision

1. **The entry is written when the image is built.** `app.Dockerfile` takes
   `TC49_UID` and `TC49_GID` as build arguments and adds a group and a passwd
   entry for them, named `tc49`, home `/tmp`, shell `nologin`, where the base
   image has none. The build runs as root, so no privilege is left behind.
2. **The values are the ones the store runs as.** `compose.yaml` passes the
   same `${TC49_UID:-1000}` and `${TC49_GID:-1000}` that make up the store's
   `user`, and `deploy.sh` exports both from `id` before `up --build`. Every
   service builds with the same arguments and so shares one image.
3. **The tables stay root's.** No `chmod`, no `group_add`, no entrypoint.

## Alternatives not taken

- **Keep the writable tables and record the trade.** It keeps a way for the
  store to become root, to save a build argument.
- **Start as root and drop with `setpriv`.** The entrypoint writes the entry
  as root and then `exec`s as the person. The privilege is short-lived, but
  the store still starts as root and the entrypoint stays on every service.
- **`nss_wrapper`.** A preloaded library answers name lookups from a file the
  uid owns. No privilege at all, at the cost of an extra package and an
  `LD_PRELOAD` on the store.

The build argument needs neither: the uid is known before the image is built,
because the same shell that builds it exports the uid it will run as.

## Consequences

- The image carries the deploying account's uid. Images are built on the box
  and never pushed anywhere, so this is not a leak.
- A box whose account changes uid gets the new name on the next deploy, which
  always rebuilds. Running the image with a uid it was not built for leaves
  that uid nameless again, and the backup fails with "No user exists".
- The `ARG` goes last in the Dockerfile, so a different uid rebuilds only that
  layer.
