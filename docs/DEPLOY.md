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

A Cloudflare API token with `DNS:Edit` on the zone, in 1Password as
**`Cloudflare DNS` in the `rails49` vault**, with the ACME account address in
the same item's `email` field. Nothing is copied out of it: `scripts/dns.sh`
reads the token at the moment it uses one, and `op run` puts it in the
environment of the `docker compose` that needs it.

The zone's id is not a secret and stands in `scripts/dns.sh` beside the zone's
name, so the token needs no permission to look one up.

```
scripts/dns.sh dev 127.0.0.1
op run --env-file=deploy/op.env -- docker compose -f deploy/compose.yaml up -d
```

The first request for the name is what makes Traefik ask for the certificate,
so give it a few seconds and then open <https://dev.rails49.org>. Renewal is
Traefik's, at about a third of the certificate's remaining life, and needs
only outbound HTTPS.

## The layout server

`blocks49.local`, a Kamrui JK06 running Ubuntu 24.04, on wifi at
`192.168.178.56`. It carries three things the dev box does not — the command
station on USB, JMRI, and a UI that is built rather than served by vite — and
the broker, which both have.

**The token cannot come from 1Password here.** `op` unlocks through the
desktop app and a headless box has none, while Traefik has to renew a
certificate months from now with nobody present. So the layout server is the
one place a secret sits on disk: `/etc/tc49/deploy.env`, owned `root:docker`
and mode 640, outside the clone, written once from a machine that does have
`op`. Revoke and rewrite it rather than editing it in place.

```
ssh blocks
cd ~/control && git pull
pnpm --dir ui build
TC49_SITE=layout docker compose --env-file /etc/tc49/deploy.env \
  -f deploy/compose.yaml --profile layout up -d
```

Nothing starts this at boot but Docker itself: every service is
`restart: unless-stopped` and the daemon is enabled, so a power cut comes back
on its own. There is no systemd unit to forget.

| runs on the layout server | port | reached how |
| --- | --- | --- |
| the app, over the certificate | 443 | `https://layout.rails49.org` |
| the broker, native clients | 1883 | the LAN address |
| the broker, a browser | 9001, and `/mqtt` | plaintext on the LAN, or through the proxy from a TLS page |
| `station`, the command station mirrored | 2560 | the LAN address |
| JMRI's desktop | 6901 noVNC, 5901 VNC | `http://192.168.178.56:6901` |
| JMRI's web server, once it is running | 12080 | the LAN address |

### The command station

A DCC-EX EX-CSB1 with an EX8874, firmware 5.4.16, on a CH340 cable. It is
named by

```
/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
```

rather than `/dev/ttyUSB0`, which renumbers, and arrives inside the `station`
container as `/dev/dccex`. The chip carries no serial number, so that path is
stable only while it is the only CH340 on the box; a second one would want
`TC49_STATION_DEVICE` set to whatever `ls /dev/serial/by-id/` then says.

Only `station` opens the device. Everything else — the `dccex` translator,
JMRI, hand-held throttles — is a client of 2560, and they coexist: every byte
the station sends reaches every client, and a client's bytes go to the station
only as whole `<…>` messages (ADR-0043).

### JMRI

An operator's tool and none of this app's business. The image does not start
JMRI: open `http://192.168.178.56:6901`, and click DecoderPro or PanelPro on
the desktop. Its profile is already pointed at the command station — a DCC++
over TCP connection to `station:2560` — and `/home/jmri` is a volume, so
whatever else is configured through the GUI survives the container.

### The router

Most home routers strip private addresses out of answers from upstream DNS —
DNS rebind protection, and it is the one thing that can break this design. A
FritzBox has it under **Home Network → Network**, the **Network Settings**
tab, at the foot of the page behind the **Change Advanced Network Settings**
button, on its **DNS Rebind Protection** tab, where `layout.rails49.org` goes
in the exception list. It is one field, it survives a reboot, and it rides
along in the configuration backup. AVM exposes no API for it, so this is the
only step here that cannot be scripted.

That button is worth naming because FRITZ!OS 8 removed the global
**Advanced View** switch every older instruction tells you to turn on first.
There is nothing to turn on any more: the advanced settings hide behind a
button on the page that owns them, and the DNS one lands directly on
`#/network/settings/critical/dns-rebind-protection`.

Reserve the layout server's address in the same router while you are there —
**Network Connections**, the device, **Home Network**, *Assign permanent IPv4
address*. The record is then set once rather than maintained.

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

One entry point, `:443`, and one route file from `deploy/routes/`, named by
`TC49_SITE` and `dev` unless it is set. A box mounts its own and no other:
Traefik asks for a certificate at startup for every router it can see, rather
than when a request for that name first arrives, so a box carrying both files
fetches a certificate for a name that is not its own.

| path | dev | layout |
| --- | --- | --- |
| `/live/<railroad>` | the bridge, `:8766`, prefix stripped | the same |
| `/mqtt` | — | the broker's websocket listener, `:9001`, prefix stripped |
| `/drawings`, `/review`, `/rosters` | vite's own proxy to the store | the store, `:8765` |
| everything else | vite, `:5173` | `ui/dist` through nginx |

`/mqtt` is there for the same reason `/live` is: a page served over TLS cannot
open a `ws://` socket, and the browser refuses it rather than warning. Native
clients go straight to 1883 and never come through the proxy.

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

**`acme: error presenting token: could not find zone`, with `SERVFAIL`** —
before writing the TXT record lego asks which zone the name belongs to, and
the resolver the network handed the container would not answer. The compose
file names `1.1.1.1` and `9.9.9.9` for that question rather than leaving it to
whatever is on hand.

**Traefik logs nothing at all** — that is success. It reports failures, so a
quiet log and a `/acme/acme.json` with bytes in it is a certificate.

**No certificate, and the log says the challenge failed** — the token is
scoped to the wrong zone, or lacks `DNS:Edit`. Renewal, and first issue, use
the same permission. `scripts/dns.sh` exercises it: if that can move a record,
the token can answer a challenge.

**Compose stops on an unset variable** — it was run without `op run`, which is
what supplies them. The message names the variable it wanted.

**The internet is down mid-session** — a `hosts` line covers the operating
console, and a phone cannot have one, so hand-held throttles are off the
layout until the name resolves again. The long TTL on `layout` is the whole
mitigation.
