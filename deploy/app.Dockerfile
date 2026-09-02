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

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
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
