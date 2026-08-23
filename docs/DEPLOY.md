# Deployment

The stack is reached at a real name over a real certificate, with nothing
inbound from the internet and nothing on the wire beyond the LAN. Why it is
built this way is [ADR-0042](adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md);
this page is how to run it.

Two names in the `rails49.org` zone, both DNS-only:

| name | points at | ttl |
| --- | --- | --- |
| `dev.rails49.org` | `127.0.0.1`, or the dev box's LAN address when a phone has to reach it | 60s |
| `layout.rails49.org` | the address the router reserves for the layout server | a day |

A public record holding a private address is the design rather than a trick.
Anyone may resolve the name; it only works on the LAN. The certificate is a
DNS-01 one, proved by writing a TXT record, so no port is forwarded and the
router is not configured.

**Everyone on the LAN can drive.** There is no authentication, on purpose, and
the reasoning is in the ADR. Do not put this behind a name reachable from
anywhere you would not hand a throttle.

## Setting it up once

A Cloudflare API token, scoped **`Zone:DNS:Edit` on `rails49.org` only**, and
the zone's id from the zone's overview page. Both go in a file outside the
repo, which Traefik and `scripts/dns.sh` both read:

```
# ~/.config/tc49/cloudflare.env
CF_DNS_API_TOKEN=…
CF_ZONE_ID=…
TRAEFIK_CERTIFICATESRESOLVERS_LE_ACME_EMAIL=you@example.com
```

Then the record, and the proxy:

```
scripts/dns.sh dev 127.0.0.1
docker compose -f deploy/compose.yaml up -d
```

The first request for the name is what makes Traefik ask for the certificate,
so give it a few seconds and then open <https://dev.rails49.org>. Renewal is
Traefik's, at about a third of the certificate's remaining life, and needs
only outbound HTTPS.

On the layout server the UI is built rather than served by vite, so nginx
serves `ui/dist` behind the same proxy:

```
pnpm --dir ui build
scripts/dns.sh layout 192.168.1.42
docker compose -f deploy/compose.yaml --profile layout up -d
```

### The router

Most home routers strip private addresses out of answers from upstream DNS —
DNS rebind protection, and it is the one thing that can break this design. A
FritzBox has it, under **Home Network → Network → Network Settings → DNS
Rebind Protection**, where `layout.rails49.org` goes in the host name
exceptions. It is one field, it survives a reboot, and it rides along in the
configuration backup. AVM exposes no API for it, so this is the only step here
that cannot be scripted.

Reserve the layout server's address in the same router while you are there.
The record is then set once rather than maintained.

## Moving a name

```
scripts/dns.sh                     what the A records say now
scripts/dns.sh dev 192.168.1.9     so a phone can reach the dev box
scripts/dns.sh dev 127.0.0.1       back again
```

`dev` carries a 60-second TTL precisely because it moves. Pointing it at the
LAN address is what testing on a phone needs; the loopback default is what
needs no maintenance when the box changes networks.

## What the proxy carries

One entry point, `:443`, and routes from `deploy/routes/`. Both boxes mount
both route files: each names its own host, so a box only ever matches its own,
and neither asks for the other's certificate. Their middlewares are named
apart for the same reason — the file provider shares one namespace across the
directory.

| path | dev | layout |
| --- | --- | --- |
| `/live/<railroad>` | the bridge, `:8766`, prefix stripped | the same |
| `/drawings`, `/review`, `/rosters` | vite's own proxy to the store | the store, `:8765` |
| everything else | vite, `:5173` | `ui/dist` through nginx |

Traefik proxies and does not read files, which is why the built UI needs
nginx behind it. Traefik rather than Caddy because its stock image carries
every ACME provider; a DNS-01 certificate under Caddy would mean building a
binary with the Cloudflare module in it.

## Why the apps bind wider than loopback

`scripts/dev.sh` starts the store and the bridge with `--host 0.0.0.0` and
vite with `server.host`. A container cannot reach a macOS host's loopback —
Docker Desktop is a virtual machine, and `host.docker.internal` reaches an
interface nothing was listening on. Both default to `127.0.0.1` and only
`dev.sh` widens them.

## When it does not work

**`Blocked request. This host is not allowed.`** — vite 6 refuses a request
whose `Host` header it does not know. The name belongs in
`server.allowedHosts` in `ui/vite.config.ts`.

**The name resolves to nothing, or to `0.0.0.0`** — DNS rebind protection at
the router, above. `dig dev.rails49.org @1.1.1.1` answers correctly while the
router does not, which is how to tell this apart from a wrong record.

**The record will not save as a private address** — it is proxied. The cloud
beside it in the dashboard has to be grey.

**No certificate, and the log says the challenge failed** — the token is
scoped to the wrong zone, or lacks `DNS:Edit`. Renewal, and first issue, use
the same permission.

**The internet is down mid-session** — a `hosts` line covers the operating
console, and a phone cannot have one, so hand-held throttles are off the
layout until the name resolves again. The long TTL on `layout` is the whole
mitigation.
