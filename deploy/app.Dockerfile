# The application in a container, and every service on the layout server runs
# from this one image with a command of its own: the store's HTTP face, the
# mirror that owns the command station's USB device (ADR-0043), and a session
# when somebody starts one. Nothing runs on that box outside a container, so
# there is no Python on it to run anything else (#354).
#
# One image rather than one per app. The apps share one `src/`, one lock file
# and one version, so a build each would cost the layout box build time for no
# isolation anybody gains: ADR-0013's deployment unit is the running container,
# and a store that carries code it never executes has crossed no boundary.
#
# The context is the repository root, so the build sees `src/`. Only the
# runtime dependencies are installed — nothing here runs the test harness —
# and the lock file is honoured so the image is the versions the repository
# was tested at.

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

# git, because the store's backup drives it: it commits the documents and
# pushes them off the machine, and a `python:slim` carries none. Without it
# the backup answers that `/store` is not a repository, which is true of every
# store and says nothing about the one it was asked about.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

# GitHub's host keys, so the first push from a box that has never spoken to
# github.com is checked against something rather than asked about: nobody is
# at a prompt in a container, and trusting whatever answers first is the wrong
# corner to cut on a box that holds a key to somebody's repository (#355).
COPY deploy/github.known_hosts /etc/ssh/ssh_known_hosts

# Somewhere for the `keys` volume to land on. Docker fills a fresh named
# volume from what the image has at that path, ownership and mode included,
# and makes it root's where the image has nothing — which the store cannot
# write, because it runs as the person who deployed the box (#387) and that
# uid is not known here. So the directory is made open to whoever the
# container turns out to be. Nothing else is in it, it is on no host path,
# and the private half ssh-keygen writes into it is 0600 on its own.
RUN mkdir /keys && chmod 1777 /keys

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./

# The dependencies in a layer of their own, ahead of the source. `src/` changes
# on nearly every deploy and `uv.lock` seldom does, and a single sync would put
# them in one layer: a source change would then re-resolve and reinstall
# packages that did not move. `--no-install-project` is what leaves the project
# itself out of this one, so the layer's only input is the lock file.
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

# Unbuffered, because what these log is connects and disconnects and they are
# only useful as they happen.
ENV PYTHONUNBUFFERED=1

# The environment is the venv's, so a service names its own program: `tc49`
# for the CLI's commands and `python -m tc49.dccex_usb` for the mirror, which
# has a command line of its own rather than a subcommand.
ENV PATH="/app/.venv/bin:$PATH"
CMD ["tc49", "--help"]
