#!/usr/bin/env bash
#
# Bring up the two servers the editor and the panel need, and leave alone
# whichever is already up.
#
#   store   http://127.0.0.1:8765   `tc49 serve`, the store's HTTP face
#   ui      http://localhost:5173    vite, which proxies the store's routes
#
# The two are written differently on purpose: vite binds [::1] and nothing
# else, so it is reached as `localhost` and not as `127.0.0.1`.
#
# Running it twice is running it once: vite holds its port strictly, so a
# second `pnpm dev` would fail rather than move to 5174, and a tab already open
# on 5173 would keep talking to the server that went away. Both are started
# detached with their output in out/dev, which is gitignored.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOGS="$ROOT/out/dev"
STORE=8765
UI=5173

mkdir -p "$LOGS"

# Whether the server on a port answers as itself, which is the question worth
# asking: a listening socket says only that the port is taken.
alive() {
  curl -fs -o /dev/null --max-time 2 "$1"
}

listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

# Start it, then wait for it to answer. A server that dies on startup — a port
# taken between the check and the bind, a missing dependency — is reported with
# its log rather than left to fail later as a browser error.
start() {
  local what=$1 port=$2 url=$3 log="$LOGS/$1.log"
  shift 3
  ("$@" >>"$log" 2>&1 &
    echo $! >"$LOGS/$what.pid")
  for _ in $(seq 40); do
    if alive "$url"; then
      printf '  %-6s %-28s started, pid %s\n' "$what" "$url" "$(cat "$LOGS/$what.pid")"
      return 0
    fi
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
    printf '  %-6s %-28s already running\n' "$what" "$url"
    return 0
  fi
  if listening "$port"; then
    echo "  port $port is taken by something that is not the $what" >&2
    return 1
  fi
  start "$what" "$port" "$url" "$@"
}

cd "$ROOT"
[ -d ui/node_modules ] || (cd ui && pnpm install)

echo "servers:"
serve store "$STORE" "http://127.0.0.1:$STORE/drawings" uv run tc49 serve
serve ui "$UI" "http://localhost:$UI/" pnpm --dir ui dev

cat <<EOF

  editor  http://localhost:$UI/
  panel   http://localhost:$UI/panel.html

logs in out/dev; stop them with: kill \$(cat $LOGS/*.pid)
EOF
