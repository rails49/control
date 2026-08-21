#!/usr/bin/env bash
#
# Bring up the servers the editor and the panel need, and leave alone
# whichever is already up.
#
#   store   http://127.0.0.1:8765   `tc49 serve`, the store's HTTP face
#   ui      http://localhost:5173   vite, which proxies the store's routes
#   bridge  ws://127.0.0.1:8766     `tc49 live`, the session the panel joins
#
#   scripts/dev.sh                     all three; pick the railroad in the
#                                      panel
#   scripts/dev.sh gotthard-v0/meet       and the session comes up running that
#                                      one
#   scripts/dev.sh gotthard-v0/meet --period 1
#                                      anything further is the session's
#   scripts/dev.sh stop                every one of them down again
#
# `start` is the word for what it does without one, and may be said —
# `scripts/dev.sh start gotthard-v0/meet`. A scenario is `folder/name`, so a
# first word that is bare `start` or `stop` is never one.
#
# The panel names the session, so the bridge always comes up: a scenario here
# is the railroad it starts on and not the one it is fixed to, and the panel
# may switch it at any time (#148).
#
# The store is always this script's, never a session's. `tc49 live` carries
# one, which would find the port taken, so the session is started with
# --no-store; the editor then survives ending a session and starting another,
# which is the way round that matters.
#
# The three are written differently on purpose: vite binds [::1] and nothing
# else, so it is reached as `localhost` and not as `127.0.0.1`, and the bridge
# is a WebSocket, reached as `ws://`.
#
# Running it twice is running it once: vite holds its port strictly, so a
# second `pnpm dev` would fail rather than move to 5174, and a tab already open
# on 5173 would keep talking to the server that went away. All are started
# detached with their output in out/dev, which is gitignored.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOGS="$ROOT/out/dev"
STORE=8765
UI=5173
BRIDGE=8766
STORE_URL="http://127.0.0.1:$STORE/drawings"
UI_URL="http://localhost:$UI/"
BRIDGE_URL="ws://127.0.0.1:$BRIDGE"

ACTION=start
case ${1-} in
  start | stop)
    ACTION=$1
    shift
    ;;
esac

SCENARIO=${1-}
[ $# -gt 0 ] && shift # what is left over belongs to `tc49 live`

if [ "$ACTION" = stop ] && [ -n "$SCENARIO" ]; then
  echo "stop takes nothing further: $SCENARIO" >&2
  exit 2
fi

mkdir -p "$LOGS"

report() {
  printf '  %-6s %-28s %s\n' "$1" "$2" "$3"
}

# Whether the server on a port answers as itself, which is the question worth
# asking: a listening socket says only that the port is taken. The bridge
# speaks WebSocket and answers a plain GET with 426 Upgrade Required, which is
# as much itself as the store's 200.
alive() {
  local url=$1 want=200
  case $url in
    ws://*)
      url="http://${url#ws://}"
      want=426
      ;;
  esac
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$url")" = "$want" ]
}

listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

# Start it, then wait for it to answer. A server that dies on startup — a port
# taken between the check and the bind, a scenario that does not exist — is
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

cd "$ROOT"

if [ "$ACTION" = stop ]; then
  echo "servers:"
  halt bridge "$BRIDGE" "$BRIDGE_URL"
  halt ui "$UI" "$UI_URL"
  halt store "$STORE" "$STORE_URL"
  exit 0
fi

[ -d ui/node_modules ] || (cd ui && pnpm install)

echo "servers:"
serve store "$STORE" "$STORE_URL" uv run tc49 serve
serve ui "$UI" "$UI_URL" pnpm --dir ui dev
# An empty scenario is no scenario at all, not the empty string: `tc49 live`
# takes it as optional, and comes up idle waiting to be told.
serve bridge "$BRIDGE" "$BRIDGE_URL" \
  uv run tc49 live ${SCENARIO:+"$SCENARIO"} --port "$BRIDGE" --no-store "$@"

cat <<EOF

  editor  http://localhost:$UI/
  panel   http://localhost:$UI/panel.html

          pick a railroad in the panel's live session menu; the session runs
          whichever one is picked

logs in out/dev; stop them with: scripts/dev.sh stop
EOF
