#!/usr/bin/env bash
#
# What a name in the zone points at, and how to change it.
#
#   scripts/dns.sh                     what the A records say now
#   scripts/dns.sh dev 127.0.0.1       back to the loopback default
#   scripts/dns.sh dev 192.168.1.42    so a phone on the same wifi can reach
#                                      the dev box
#
# Public DNS is allowed to carry a private address: anyone may resolve the
# name, and it only works on the LAN (ADR-0042). The record is DNS-only —
# a proxied record will not accept a private address — and the certificate
# comes from a TXT challenge, so nothing here is inbound.
#
# `dev` is the one that moves, so its TTL is short; `layout` is set once when
# the router's reservation is known and wants a long one, which is all that
# stands between a session and an ISP outage.
#
# The token is the same one Traefik renews with, `Zone:DNS:Edit` on the one
# zone, beside the zone's id so no second permission is needed to find it.

set -euo pipefail

ENV_FILE=${TC49_CLOUDFLARE_ENV:-$HOME/.config/tc49/cloudflare.env}
ZONE_NAME=rails49.org
API=https://api.cloudflare.com/client/v4

if [ ! -f "$ENV_FILE" ]; then
  echo "no $ENV_FILE; see docs/DEPLOY.md" >&2
  exit 2
fi
# shellcheck disable=SC1090
. "$ENV_FILE"
: "${CF_DNS_API_TOKEN:?not set in $ENV_FILE}"
: "${CF_ZONE_ID:?not set in $ENV_FILE}"

api() {
  local method=$1 path=$2
  shift 2
  curl -sS -X "$method" "$API$path" \
    -H "Authorization: Bearer $CF_DNS_API_TOKEN" \
    -H "Content-Type: application/json" "$@"
}

# Cloudflare answers every call with `success` and an `errors` list, including
# the ones that arrive as 200. Reading it here means a failure is reported as
# what Cloudflare said rather than as a later record that quietly did not move.
field() {
  python3 -c '
import json, sys
answer = json.load(sys.stdin)
if not answer.get("success"):
    sys.exit("; ".join(e.get("message", "?") for e in answer.get("errors", [])) or "refused")
records = answer["result"]
if sys.argv[1] == "list":
    for record in sorted(records, key=lambda r: r["name"]):
        print("  %-28s %-16s ttl %s" % (record["name"], record["content"], record["ttl"]))
else:
    print(records[0]["id"] if records else "")
' "$1"
}

if [ $# -eq 0 ]; then
  echo "$ZONE_NAME:"
  api GET "/zones/$CF_ZONE_ID/dns_records?type=A" | field list
  exit 0
fi

if [ $# -ne 2 ]; then
  echo "usage: scripts/dns.sh [<name> <address>]" >&2
  exit 2
fi

NAME=$1.$ZONE_NAME
ADDRESS=$2
# Short for the name that moves, a day for the one that does not. A cached
# answer must not outlive a flip, and must outlive a blip.
TTL=60
[ "$1" = layout ] && TTL=86400

ID=$(api GET "/zones/$CF_ZONE_ID/dns_records?type=A&name=$NAME" | field id)
BODY=$(printf '{"type":"A","name":"%s","content":"%s","ttl":%d,"proxied":false}' \
  "$NAME" "$ADDRESS" "$TTL")

if [ -n "$ID" ]; then
  api PATCH "/zones/$CF_ZONE_ID/dns_records/$ID" --data "$BODY" >/dev/null
else
  api POST "/zones/$CF_ZONE_ID/dns_records" --data "$BODY" >/dev/null
fi

echo "$NAME -> $ADDRESS (ttl $TTL)"
