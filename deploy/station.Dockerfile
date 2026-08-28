# The `station` app in a container, because it is the one app that must be on
# the layout server: it owns the command station's USB device (ADR-0043).
# #219 builds the app and leaves the image here, with the rest of deployment.
#
# The context is the repository root, so the build sees `src/`. Only the
# runtime dependencies are installed — a mirror of a serial port needs no test
# harness — and the lock file is honoured so the image is the versions the
# repository was tested at.

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Unbuffered, because what this logs is connects and disconnects and they are
# only useful as they happen.
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "tc49.station"]
CMD ["--device", "/dev/dccex", "--port", "2560"]
