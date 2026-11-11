# The `web` service's image, `control-web`: node builds the UI, nginx serves
# what came out (rails49/.github#71 decision 6). A box then needs no node or
# pnpm, and `ui/dist` is no longer mounted from the clone.
#
# The context is the repository root, so the build sees `ui/` and `deploy/`.
# `.dockerignore` keeps the host's `node_modules` and a previous `dist` out.

FROM node:24-alpine AS build

# The pnpm major the workflow installs with (`.github/workflows/ci.yml`).
RUN npm install -g pnpm@11

WORKDIR /ui

# The dependencies in a layer of their own, ahead of the sources, which change
# far more often than the lock file.
COPY ui/package.json ui/pnpm-lock.yaml ui/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY ui/ ./
RUN pnpm run build

FROM nginx:alpine

# `index.html` with `Cache-Control: no-cache` (#1123).
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /ui/dist /usr/share/nginx/html

# The commit this was built from (dccex ADR-0005 d.4), last so a new commit
# rebuilds nothing above. Empty where nobody named one.
ARG CONTROL_COMMIT=
LABEL org.opencontainers.image.revision=$CONTROL_COMMIT \
    org.opencontainers.image.source=https://github.com/rails49/control
