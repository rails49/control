#!/usr/bin/env bash
#
# Bring up the servers the app needs, and leave alone whichever is already up.
#
#   store   http://127.0.0.1:8765   `tc49 serve`, the store's HTTP face
#   ui      http://localhost:5173   vite, which proxies the store's routes
#   broker  ws://127.0.0.1:9001     mosquitto, the bus every app is a client of
#
#   scripts/dev.sh        all three
#   scripts/dev.sh stop   every one of them down again
#
# `start` is the word for what it does without one, and may be said —
# `scripts/dev.sh start`.
#
# **No app is started here.** Each of them is its own process with a command
# line of its own (ADR-0059, decision 5) and comes up alone against an empty
# broker, so which ones a developer wants is theirs to say. A simulated
# railroad the run view can drive is one of them:
#
#   uv run python -m tc49.simulator --broker 127.0.0.1:1883 \
#     --railroad reversing-loops --store http://127.0.0.1:8765
#
# and the scheduler, the dispatcher and the driver take the same three flags.
# The run view reads which railroad the broker runs off the row the layout
# interface publishes, so the app follows whichever railroad these are started
# on. The band's picker can ask for another (ADR-0060), but only while
# `tc49/layout/state/power` reads `off` — and the simulator pins its power to
# `on` (ADR-0030), so in front of the simulator started above the picker is
# inert. Whether the simulated binding should be exempt is open on #394.
#
# The store is rooted at this checkout's `bench/`, the benchmark fixtures, and
# not at the `~/tc49` an installation reads (#320): the railroads a developer
# working on the app wants are those. Export TC49_STORE to work on your own
# instead, and pass the same store URL to whatever apps you start.
#
# The store and vite bind every interface rather than loopback, because the
# reverse proxy serving `dev.rails49.org` runs in a container and cannot reach
# a macOS host's loopback (ADR-0042, docs/DEPLOY.md). They are still reached
# here as loopback, which is one of the interfaces bound. The broker publishes
# its two ports the same way, and the proxy reaches 9001 as `/mqtt`.
#
# The broker is a container and not a process: mosquitto is nobody's Python
# dependency and the deployment runs the stock image (deploy/compose.yaml). It
# is started with `docker run` rather than through that file, because compose
# demands the proxy's Cloudflare token in the environment for any service it is
# asked for and a developer bringing up a bus has no business with one.
#
# Running it twice is running it once: vite holds its port strictly, so a
# second `pnpm dev` would fail rather than move to 5174, and a tab already open
# on 5173 would keep talking to the server that went away. The two host servers
# are started detached with their output in out/dev, which is gitignored; the
# broker's log is `docker logs`.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOGS="$ROOT/out/dev"
STORE=8765
UI=5173
MQTT=1883
BROKER=9001
BROKER_NAME=tc49-broker
STORE_URL="http://127.0.0.1:$STORE/drawings"
STORE_ROOT=${TC49_STORE:-$ROOT/bench}
UI_URL="http://localhost:$UI/"
BROKER_URL="ws://127.0.0.1:$BROKER"

ACTION=start
case ${1-} in
  start | stop)
    ACTION=$1
    shift
    ;;
esac

if [ $# -gt 0 ]; then
  echo "takes nothing further: $*" >&2
  exit 2
fi

mkdir -p "$LOGS"

report() {
  printf '  %-6s %-28s %s\n' "$1" "$2" "$3"
}

# Whether the server on a port answers as itself, which is the question worth
# asking: a listening socket says only that the port is taken.
alive() {
  local url=$1
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$url")" = "200" ]
}

listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

# Start it, then wait for it to answer. A server that dies on startup — a port
# taken between the check and the bind, a railroad that does not exist — is
# reported with its log rather than left to fail later as a browser error, and
# a process already gone is not waited on for the rest of the ten seconds.
start() {
  local what=$1 port=$2 url=$3 log="$LOGS/$1.log" pid
  shift 3
  ("$@" >>"$log" 2>&1 &
    echo $! >"$LOGS/$what.pid")
  pid=$(cat "$LOGS/$what.pid")
  for _ in $(seq 40); do
    if alive "$url"; then
      report "$what" "$url" "started, pid $pid"
      return 0
    fi
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  echo "  $what failed to come up on $port; see $log" >&2
  tail -5 "$log" >&2
  return 1
}

serve() {
  local what=$1 port=$2 url=$3
  shift 3
  if alive "$url"; then
    report "$what" "$url" "already running"
    return 0
  fi
  if listening "$port"; then
    echo "  port $port is taken by something that is not the $what" >&2
    return 1
  fi
  start "$what" "$port" "$url" "$@"
}

# Take down what this script started, which is what has a pidfile. A server
# somebody else started is left alone and said so: `stop` undoes `start` and is
# not a way to clear a port.
#
# The recorded pid fronts the server rather than being it — `uv run` and `pnpm`
# each hand off to a child — so the port is watched, not the process, and a
# child still holding it after its parent is gone is killed by the port. A vite
# outliving its `pnpm` is exactly the half-stopped state that leaves the next
# `start` refusing to bind.
halt() {
  local what=$1 port=$2 url=$3 file="$LOGS/$1.pid" pid=""
  [ -f "$file" ] && pid=$(cat "$file")
  if [ -z "$pid" ]; then
    if listening "$port"; then
      report "$what" "$url" "left alone, started elsewhere"
    else
      report "$what" "$url" "not running"
    fi
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  rm -f "$file"
  for _ in $(seq 20); do
    listening "$port" || break
    sleep 0.25
  done
  if listening "$port"; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN -t | xargs kill 2>/dev/null || true
  fi
  report "$what" "$url" "stopped"
}

# The broker, as a container. A container this script started is the one
# wearing its name; anything else on the port is somebody else's and is left
# alone, which is what the two host servers do too.
broker_up() {
  if listening "$BROKER"; then
    if docker inspect "$BROKER_NAME" >/dev/null 2>&1; then
      report broker "$BROKER_URL" "already running"
    else
      report broker "$BROKER_URL" "left alone, started elsewhere"
    fi
    return 0
  fi
  docker rm -f "$BROKER_NAME" >/dev/null 2>&1 || true
  if ! docker run -d --name "$BROKER_NAME" \
    -p "$MQTT:1883" -p "$BROKER:9001" \
    -v "$ROOT/deploy/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" \
    eclipse-mosquitto:2 >"$LOGS/broker.log" 2>&1; then
    echo "  broker failed to start; see $LOGS/broker.log" >&2
    return 1
  fi
  for _ in $(seq 40); do
    listening "$BROKER" && break
    sleep 0.25
  done
  if ! listening "$BROKER"; then
    echo "  broker failed to come up on $BROKER; see: docker logs $BROKER_NAME" >&2
    return 1
  fi
  report broker "$BROKER_URL" "started"
}

broker_down() {
  if ! docker inspect "$BROKER_NAME" >/dev/null 2>&1; then
    if listening "$BROKER"; then
      report broker "$BROKER_URL" "left alone, started elsewhere"
    else
      report broker "$BROKER_URL" "not running"
    fi
    return 0
  fi
  docker rm -f "$BROKER_NAME" >/dev/null 2>&1 || true
  report broker "$BROKER_URL" "stopped"
}

cd "$ROOT"

if [ "$ACTION" = stop ]; then
  echo "servers:"
  broker_down
  halt ui "$UI" "$UI_URL"
  halt store "$STORE" "$STORE_URL"
  exit 0
fi

[ -d ui/node_modules ] || (cd ui && pnpm install)

echo "servers:"
serve store "$STORE" "$STORE_URL" \
  uv run tc49 serve --host 0.0.0.0 --store "$STORE_ROOT"
serve ui "$UI" "$UI_URL" pnpm --dir ui dev
broker_up

cat <<EOF

  app     http://localhost:$UI/          the run view
          http://localhost:$UI/#edit     the editor

          the run view shows whichever railroad the apps on this broker are
          running; start one, for example:

          uv run python -m tc49.simulator --broker 127.0.0.1:$MQTT \\
            --railroad reversing-loops --store http://127.0.0.1:$STORE

logs in out/dev, and: docker logs $BROKER_NAME
stop them with: scripts/dev.sh stop
EOF
