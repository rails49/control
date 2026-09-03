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

The clone pulls over ssh — `git@github.com:rails49/control.git` — with the key
that is already on the box. The repository is public, so HTTPS needs no
credential for it, but GitHub challenges the second request of an anonymous
fetch often enough that an unattended pull stops to ask for a username. Over
ssh there is nothing to ask.

```
ssh blocks
cd ~/control && git pull
pnpm --dir ui build
TC49_SITE=layout docker compose --env-file /etc/tc49/deploy.env \
  -f deploy/compose.yaml --profile layout up -d --remove-orphans
```

`scripts/deploy.sh` is that sequence, run over ssh from the dev box.

A route file change needs the proxy recreated, not just recomposed: the file
is bind-mounted one file deep, so a `git pull` replaces the inode and the
container keeps the one it started with. That is [#353](https://github.com/rails49/control/issues/353);
until it lands, `--force-recreate proxy`.

`--remove-orphans` is there because a container whose service was renamed
keeps running under the old name and keeps its published port. After
[#299](https://github.com/rails49/control/issues/299) the `station` container
held 2560, and `dccex-usb` could not start until it was gone.

Nothing starts this at boot but Docker itself: every service is
`restart: unless-stopped` and the daemon is enabled, so a power cut comes back
on its own. There is no systemd unit to forget.

**Nothing runs on that box outside a container**, and there is no Python on it
to run anything else (#354). Every service below is built from one image,
`deploy/app.Dockerfile`, with a command of its own.

| runs on the layout server | port | reached how |
| --- | --- | --- |
| the app, over the certificate | 443 | `https://layout.rails49.org` |
| the redirect to it | 80 | `layout.rails49.org` typed bare |
| the store's HTTP face | 8765, container-only | `/backup`, `/drawings`, `/review`, `/rosters` |
| the broker, native clients | 1883 | the LAN address |
| the broker, a browser | 9001, and `/mqtt` | plaintext on the LAN, or through the proxy from a TLS page |
| `dccex-usb`, the command station mirrored | 2560 | the LAN address |
| JMRI's desktop | 6901 noVNC, 5901 VNC | `http://192.168.178.56:6901` |
| JMRI's web server, once it is running | 12080 | the LAN address |

### The store, and the documents it serves

The store is always on, because the documents are the one thing there that is
nobody's run: the editor reads and writes them whether or not a railroad is
moving. It is rooted at `~/tc49` on the box, bind-mounted in, which is a
directory rather than a docker volume so it stays somewhere to `cd` into and
push from (#320). `TC49_STORE` moves it.

A fresh box has no `~/tc49` and the bind mount makes one. An empty store is an
ordinary state and not a fault — nothing seeds it, by decision — so the server
comes up, answers, and lists nothing until somebody draws. The directory is
written by the container and so is owned by root on the host; nothing on the
host needs to write it, and turning the store into a git repository happens
through the app rather than a terminal (#355): the backup dialog shows the
key the store made for itself and takes the address of an empty repository
the person made. That key lives in the `keys` docker volume — outside the
store, so no commit can carry it, and on no host path — and GitHub's host keys
are in the image, so the first push is checked against them rather than asked
about ([store/BACKUP.md](store/BACKUP.md)).

### Running a session

A session is a run of one railroad, with an operator, and not a daemon — so it
is started deliberately and `/live` answers 502 until it is:

```
ssh blocks
cd ~/control
TC49_RAILROAD=gotthard docker compose --env-file /etc/tc49/deploy.env \
  -f deploy/compose.yaml --profile session up -d session
docker attach deploy-session-1
```

Attaching is not optional housekeeping: a session driving the command station
reads its own input, which is where a person types the block readings no
detector publishes yet (#315). Detach with `ctrl-p ctrl-q`, which leaves it
running; `ctrl-c` stands the railroad down and ends the run.

It reaches the command station through `dccex-usb:2560` rather than the device
— which is what lets JMRI and a hand-held throttle share one station
(ADR-0043) — and reads the same `~/tc49` the store serves.

### The command station

A DCC-EX EX-CSB1 with an EX8874, firmware 5.4.16, on a CH340 cable. It is
named by

```
/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
```

rather than `/dev/ttyUSB0`, which renumbers, and arrives inside the
`dccex-usb` container as `/dev/dccex`. The chip carries no serial number, so
that path is stable only while it is the only CH340 on the box; a second one
would want `TC49_STATION_DEVICE` set to whatever `ls /dev/serial/by-id/` then
says.

Only `dccex-usb` opens the device. Everything else — the `dccex` translator,
JMRI, hand-held throttles — is a client of 2560, and they coexist: every byte
the command station sends reaches every client, and a client's bytes go to it
only as whole `<…>` messages (ADR-0043).

### JMRI

An operator's tool and none of this app's business. The image does not start
JMRI: open `http://192.168.178.56:6901`, and click DecoderPro or PanelPro on
the desktop. Its profile is already pointed at the command station — a DCC++
over TCP connection to `dccex-usb:2560` — and `/home/jmri` is a volume, so
whatever else is configured through the GUI survives the container.

That volume is why renaming the service
([#299](https://github.com/rails49/control/issues/299)) needs a click here.
Compose's DNS follows the service name, and a profile saved before the rename
still holds the old one, which no longer resolves: open DecoderPro, set the
connection's host to `dccex-usb`, and save. Nothing else moves — the published
port is still 2560, and everything reaching it by LAN address reaches it
unchanged.

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

Two entry points and one route file from `deploy/routes/`, named by
`TC49_SITE` and `dev` unless it is set. The routers all sit on `:443`. `:80`
carries a redirect to it and holds no router of its own, because a person types
a bare hostname and the browser tries http first; a box publishing 443 alone
refuses that connection and reads as down. The certificate comes from a DNS-01
challenge, so nothing needs `:80` reachable from outside the LAN.

A box mounts its own route file and no other:
Traefik asks for a certificate at startup for every router it can see, rather
than when a request for that name first arrives, so a box carrying both files
fetches a certificate for a name that is not its own.

| path | dev | layout |
| --- | --- | --- |
| `/live/<railroad>` | the bridge, `:8766`, prefix stripped | the same |
| `/mqtt` | — | the broker's websocket listener, `:9001`, prefix stripped |
| `/backup`, `/drawings`, `/review`, `/rosters` | vite's own proxy to the store | the store, `:8765` |
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

**noVNC serves its page on 6901 but Connect fails** — the VNC server came up
on a display other than `:1`, and the page dials 5901 regardless. The image's
`vncserver` takes the first display with no socket in `/tmp/.X11-unix`, and a
restart that keeps the writable layer leaves the old one behind, so each
restart moves the server one port further away. `tmpfs: [/tmp]` on the `jmri`
service in `deploy/compose.yaml` gives it an empty `/tmp` every start, which
is what keeps it on `:1` and 5901.

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
