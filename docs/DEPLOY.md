# Deployment

The stack is reached at a real name over a real certificate, with nothing
inbound from the internet and nothing on the wire beyond the LAN. Why it is
built this way is [ADR-0042](adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md);
this page is how to run it.

**The name, the certificate and the door are the installation's.** A box
installs [`rails49/installation`](https://github.com/rails49/installation)
before any railroad. That repository holds the door — the one thing in front
of everything a browser reaches on the box — the certificate for the box's
name, the page listing what the box serves, and the box's declaration of
itself. `control` installs on top of it and carries no proxy, no entry point on
80 or 443, no ACME credential and no route file
([#557](https://github.com/rails49/control/issues/557)): being reachable
stopped being a railroad's business.

What is left to this page is the railroad — the containers, the store's
documents, the command station — and the two files on the box they are started
against.

**Everyone on the LAN can drive.** There is no authentication, on purpose, and
the reasoning is in the ADR. Do not put this behind a name reachable from
anywhere you would not hand a throttle.

## What the box declares

`/etc/rails49/box.env`, written once when the installation is installed and
read by every stack on the box:

| variable | what it says | on this box |
| --- | --- | --- |
| `BOX_DOMAIN` | the name the box is reached at | `gleis49.org` |
| `BOX_UIS` | the UIs it serves, one label each | `control jmri` |
| `BOX_ACME_PROVIDER` | the DNS provider that issues its certificates | `cloudflare` |

So this UI is at <https://control.gleis49.org>, and naming a box is editing one
file on the box rather than forking this repository. An `A` record for the apex
and one per label, each holding the box's LAN address, is the installation's
step and its README is where it is written; a public record holding a private
address is the design rather than a trick, since anyone may resolve the name
and it only works on the LAN.

`/etc/rails49/acme.env` sits beside the declaration and holds the credential
the certificate is renewed with. **The door is the only thing that reads it**,
so handing `control` the declaration does not hand it the box's DNS
credentials — and the declaration stays something you can paste into an issue
while debugging a headless box.

`control` adds one file of its own in that directory,
`/etc/rails49/deploy.env`: which railroad the apps come up on, where the store
is rooted, which device the command station is on. One directory rather than
two, so the box has one place its settings sit.

## Working on the app

`scripts/dev.sh` needs none of this. It starts vite on `localhost:5173`, the
store on 8765 and the broker beside them — no name, no certificate and no
door, because `localhost` is a secure context and the browser asks for nothing
more. A developer who wants the real shape runs the installation on their own
machine, writes a declaration for it, and starts this stack against it the way
a box does.

## The layout server

`gleis49.org`, a Kamrui JK06 running Ubuntu 24.04, on wifi at
`192.168.178.56`. It carries three things a development machine does not — the
command station on USB, JMRI, and a UI that is built rather than served by
vite — and the broker, which both have. The installation is already on it, so
the door is up, the certificate is real, and `https://control.gleis49.org`
answers 404 until this stack is started.

**The ACME credential cannot come from 1Password here.** `op` unlocks through
the desktop app and a headless box has none, while the door has to renew a
certificate months from now with nobody present. So `/etc/rails49/acme.env` is
where that secret sits on disk, owned `root:docker` and mode 640, outside every
clone, written once from a machine that does have `op`. Revoke and rewrite it
rather than editing it in place. It is the installation's file and `control`
never reads it; `control`'s own `/etc/rails49/deploy.env` beside it holds no
secret at all.

**`rails49` is an ssh alias**, and it is a convenience rather than something
the deploy needs. `scripts/deploy.sh` names `ttmetro@gleis49.org` in
full, because the alias lives in `~/.ssh/config` — a personal file that
collects every host its owner has ever reached, is in no repository, and once
lost the stanza and took the deploy down with it (#488, #496). Nothing that
runs unattended may depend on a file like that.

What you type by hand is still `ssh rails49`, here and further down the page.
The stanza sits in `~/.ssh/config` itself and is in no repository at all, which
is the reason the paragraph above exists rather than an oversight: a machine
that has never seen it deploys anyway. On one that wants the alias, add it:

```ssh-config
Host gleis49 rails49
    HostName gleis49.org
    User ttmetro
```

Two names for one box. `gleis49` is what the box is called and is what to
reach for; `rails49` is the project's name and is what this page and years of
typing already say, so dropping it would break a line somebody has written
down.

`HostName` is the DNS name rather than `rails49.local` on purpose: the record
is independent of what the box calls itself, so renaming the machine cannot cut
off the deploy. It had to survive exactly that when the host was renamed from
`blocks49`.

The account is named here, on a public page, and what that costs depends on the
box rather than on this project's design. [ADR-0042](adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)
says everyone on the LAN may drive the railroad; it says nothing about who may
open a shell, which is a separate surface with real authentication. **The box is
key-only.** `PasswordAuthentication no` sits in
`/etc/ssh/sshd_config.d/50-cloud-init.conf`, the file the installer had left at
`yes` ([#497](https://github.com/rails49/control/issues/497)); check it with
`sudo sshd -T | grep -i passwordauthentication`. A published name is half of a
login only where a password can complete it, so naming the account costs
nothing. A new machine gets in by having its public key added to
`~/.ssh/authorized_keys` on the box; there is no password to fall back on.

**This installation's own deploy facts stay in this repository** — the LAN
address above, the zone, the box, the account — even though
[#318](https://github.com/rails49/control/issues/318) moved an installation's
*documents* out to a store of its own. The two are different kinds of thing: a
railroad, its stock and its decoder addresses are a user's data and drift as
the layout changes, while this page is how this project's own stack is run.
Splitting it would leave a general page nobody can follow beside a private one
nobody reviews.

**The box pulls over HTTPS — `https://github.com/rails49/control.git`.** The
repository is public, so an anonymous fetch needs no credential: nothing is
registered on GitHub for this box, there is no key to rotate, and there is no
secret on its disk beyond the door's `acme.env`. `scripts/deploy.sh` exports
`GIT_TERMINAL_PROMPT=0`, so a request for a username fails loudly rather than
reading the rest of the deploy as the answer.

Clone with that URL, and a box that was cloned with another one still deploys:
`scripts/deploy.sh` sets the remote before every pull, and prints the URL it
replaced when it replaced one. Which remote a box pulls from is state outside
the checkout — a line in `.git/config` on that one machine — and it took the
deploy down on 2026-09-20, when the box's ssh remote met a key GitHub no longer
accepted ([#541](https://github.com/rails49/control/issues/541)). It is the
same fault as the ssh alias, and gets the same answer: the deploy depends on
nothing that is not in this checkout.

The deploy carries that line itself rather than calling a script under
`scripts/`, the way it calls `store-root.sh` below. It runs before the pull,
and what is under `scripts/` on the box is whatever the box last pulled —
which on a box that cannot pull is nothing
([#543](https://github.com/rails49/control/issues/543)).

**The shared network is the installation's**, made under a fixed name every
stack on the box joins — see
[What the containers declare](#what-the-containers-declare). Three of the
containers below join it and compose starts none of them without it, so a box
that has not installed the installation is told so before anything comes up.

```
ssh rails49
cd ~/control
git remote set-url origin https://github.com/rails49/control.git
git pull
pnpm --dir ui build
mkdir -p "$(scripts/store-root.sh /etc/rails49/deploy.env)"
[ -f /etc/rails49/dccex-startup.txt ] ||
  { sudo rm -rf /etc/rails49/dccex-startup.txt &&
    sudo install -m 644 /dev/null /etc/rails49/dccex-startup.txt; }
export TC49_UID=$(id -u) TC49_GID=$(id -g)
docker compose --env-file /etc/rails49/box.env \
  --env-file /etc/rails49/deploy.env \
  -f deploy/compose.yaml --profile layout --profile hardware \
  up -d --remove-orphans
```

`scripts/deploy.sh` is that sequence, run over ssh from a development machine.

**Two `--env-file`s, because two things are being said.** The first is the
box's declaration, which every stack on the box is started against and which
is where the name in the routers' labels comes from; the second is this
stack's own settings. A box with no declaration is told which variable is
missing rather than given routers under a blank name.

**Every `docker compose` here takes both**, `logs` and `ps` included: compose
reads the whole file before it runs any subcommand, so one without them stops
on the missing name rather than on anything to do with what was asked.

**Two profiles, because a box is software plus whatever is wired to it.**
`layout` is the software of a running railroad: the store, the built ui, and
the scheduler, dispatcher, driver and layout interface, each its own
container (ADR-0059, decision 5). `hardware` is what this box owns because of
what is plugged into it, which here is the translator that speaks to the
command station. A box with no steel under it asks for `sim` in place
of `hardware`, which runs the simulator where the layout interface's hardware
binding would be, and `tests/system/test_compose.py` holds the split.

Which railroad the apps come up on is `TC49_RAILROAD` in that env file. It is
a starting point and not a binding: a person loads another railroad from the
app while they run, and every app follows without a restart
([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).

**It has no default, and a box that names none comes up with no railroad.**
An app with none **stands**: it is up, it publishes nothing, and it is built
on the first railroad named that the store can give. So a box that has done
nothing but install reaches a steady state with nothing restarting, and what
it is waiting for is a railroad to exist — see
[the store, and the documents it serves](#the-store-and-the-documents-it-serves).
A default naming a railroad would be a default that cannot resolve: nothing
seeds a store, and the railroads in this repository are fixtures under
`bench/` that are on nobody's box. `gotthard` was that default until
[#564](https://github.com/rails49/control/issues/564), and it named no drawing
anywhere, so a box following this page ended with four containers in a restart
loop.

`--remove-orphans` is there because a container whose service was renamed
keeps running under the old name and keeps its published port. After
[#299](https://github.com/rails49/control/issues/299) the `station` container
held 2560, and `dccex-usb` could not start until it was gone.

**The containers are `tc49-…`.** The compose file names its own project
([#451](https://github.com/rails49/control/issues/451)) rather than letting
compose take the name from the `deploy/` directory, so `docker logs
tc49-store-1` is the same container on every clone. Addressing a service
rather than a container — `docker compose --env-file /etc/rails49/box.env
--env-file /etc/rails49/deploy.env -f deploy/compose.yaml logs scheduler` —
needs no name at all.

Nothing starts this at boot but Docker itself: every service is
`restart: unless-stopped` and the daemon is enabled, so a power cut comes back
on its own. There is no systemd unit to forget.

**Nothing runs on that box outside a container**, and there is no Python on it
to run anything else (#354). Every service below is built from one image,
`deploy/app.Dockerfile`, with a command of its own.

Nothing here publishes 80 or 443: those are the door's, and it is the
installation's container. What the door serves is a label under the box's
name, and what the containers below publish is on the LAN beside it.

| runs on the layout server | port | reached how |
| --- | --- | --- |
| the app, over the certificate | the door's 443 | `https://control.gleis49.org` |
| the store's HTTP face | 8765, container-only | `/backup`, `/drawings`, `/review`, `/layouts`, `/rosters`, `/catalogue` under that name |
| the broker, native clients | 1883 | the LAN address |
| the broker, a browser | 9001, and `/mqtt` | plaintext on the LAN, or through the door from a TLS page |

The command station is mirrored on 2560 at the LAN address, and that port is
not this file's: it is published by [`rails49/dccex`](https://github.com/rails49/dccex),
a stack of its own on the same box.

### The store, and the documents it serves

The store is always on, because the documents are the one thing there that is
nobody's run: the editor reads and writes them whether or not a railroad is
moving. It is rooted at `~/tc49` on the box, bind-mounted in, which is a
directory rather than a docker volume so it stays somewhere to `cd` into and
push from (#320). `TC49_STORE` moves it, in the env file or in the shell the
deploy runs from.

**The directory and everything in it belong to the person who deployed the
box.** `scripts/deploy.sh` makes it before it runs compose, because a bind
mount whose source is missing is created by the Docker daemon as root, and
that shut the person out of their own documents — no editing, no `git init`,
no catalogue put in by hand (#387). Which directory that is,
`scripts/store-root.sh` answers, the way compose answers it: the deploy
shell's `TC49_STORE` first, then the env file's, then `~/tc49`. Expanding it
in the deploy shell made `~/tc49` on a box that had moved its store in the
env file, and the daemon then made the real one as root after all (#442).
The store then runs as that
person, `TC49_UID` and `TC49_GID` from `id` on the box and uid 1000 where
neither is set, so every drawing the editor saves and every object the backup
commits is theirs on the host too. `cd` into it, edit it, make it a
repository and push from it: the app's git and yours see the same store,
owned by the same person.

A fresh box has no `~/tc49`, and an empty store is an ordinary state and not
a fault — nothing seeds it, by decision — so the server comes up, answers,
and lists nothing until somebody draws. **The apps in the same profile are up
too**, standing with no railroad rather than exiting over one they cannot
read: draw a railroad in the editor and they are built on it the moment one is
named, and nothing has to be restarted for it
([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md),
[#564](https://github.com/rails49/control/issues/564)). Until then the only
thing on the bus is the store, which is what makes the editor the way a first
railroad is drawn.

Turning the store into a git repository is offered through the app rather
than needing a terminal (#355): the backup dialog shows the key the store made
for itself and takes the address of an empty repository the person made. That key lives in the `keys`
docker volume — outside the store, so no commit can carry it, and on no host
path — and GitHub's host keys are in the image, so the first push is checked
against them rather than asked about ([store/BACKUP.md](store/BACKUP.md)).
The volume is made writable by that uid in the image.

**What the uid is called, the image answers.** ssh will not run for a uid it
cannot name — `No user exists for uid 501` — and the store makes its key with
`ssh-keygen` and pushes with `ssh`, so a nameless uid is a backup that cannot
be made at all. The box's own passwd and group tables came into the store
read-only for this, which answered it only on a box that keeps its people in
those files: a mac keeps them in Open Directory, hands the store uid 501, and
the feature was unreachable there
([#566](https://github.com/rails49/control/issues/566)). The image names it
instead: compose builds it with `TC49_UID` and `TC49_GID` as build arguments,
and the build adds a passwd and a group entry for them where the base image
has none. The tables stay root's and read-only to the store, so nothing running
in the container can add a user to them
([ADR-0067](adr/0067-the-image-names-the-store-uid-at-build.md)). **The uid is
still the person's** — nothing about whose the documents are changes. A box
whose account changes uid gets the new name on its next deploy, which rebuilds
the image anyway.

**A box deployed before the store ran as the person is fixed by removing that
volume once.** Docker fills a named volume from the image only while the
volume is empty, so a `keys` volume made before
[#387](https://github.com/rails49/control/issues/387) is still root's and no
later deploy re-makes it. The store, running as uid 1000, then finds a key it
can see and cannot open: the public half is world-readable, so the backup
dialog used to show a key that looked fine while every push under it was
refused ([#443](https://github.com/rails49/control/issues/443)). It says so
now, and what it asks for is this. The volume is `deploy_keys` on a box
deployed before the project named itself and `tc49_keys` since
([#451](https://github.com/rails49/control/issues/451)); `docker volume ls`
says which. Only the store mounts it, so nothing else comes down:

```
cd ~/control
docker compose --env-file /etc/rails49/box.env \
  --env-file /etc/rails49/deploy.env -f deploy/compose.yaml rm -sf store
docker volume rm deploy_keys
docker compose --env-file /etc/rails49/box.env \
  --env-file /etc/rails49/deploy.env -f deploy/compose.yaml up -d --no-deps store
```

The store makes itself a new key on the next `File ▸ Backup…`, in a volume
seeded from the image and owned by that person. Paste its public half into the
repository under *Settings ▸ Deploy keys* with *Allow write access*, and delete
the old one if it is still listed. The key is the box's identity and nothing
else of yours, so losing it costs that re-registration and nothing more.

**Deploy keys have to be allowed for the organisation that holds the
repository.** `deploy_keys_enabled_for_repositories` off forbids the whole
mechanism for every repository under that organisation, so a box rebuilt into
one gets a key the store can read and GitHub will not accept — a different
fault reaching the same dead backup. It is an organisation setting and not a
repository one, so no amount of work on the box finds it.

### Typing the block readings

No camera publishes `tc49/layout/state/device/sensor` yet, so on a physical
railroad the levels that complete a move are typed by a person. That keyboard
is a client of the broker like any app, and runs from a checkout rather than
from compose — it is one process reading one terminal's input, and nothing
about it wants restarting (ADR-0059, decision 5, #379):

```
ssh rails49
cd ~/control
uv run tc49 readings --broker 127.0.0.1:1883 \
  --railroad <the railroad the box is running> --store http://127.0.0.1:8765
```

Type `<block>.<end> <level>` a line at a time; `ctrl-c` ends it, and the
railroad goes on running without it. The apps themselves are the compose
services above and are already up; which of `layout` and `simulator` a box
runs is what makes it steel or a simulation, and neither is started by hand.

### The command station

A DCC-EX EX-CSB1 with an EX8874 on a CH340 cable. **The mirror that owns its
USB device is [`rails49/dccex`](https://github.com/rails49/dccex)**, a compose
project of its own on this box, and what is deployed from here is a client of
the 2560 it publishes. Which firmware build is on the station, and writing a
new one onto it, are that project's and are not written here: a page kept by
hand would go stale the first time somebody wrote a new one.

Deploying this stack for the first time after the split takes the old
`dccex-usb` container with it, `--remove-orphans` being the flag above that
sweeps a service this file no longer has. Bring the mirror's own project up
first, or the railroad comes back with no station on 2560. The device is
named by

```
/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
```

rather than `/dev/ttyUSB0`, which renumbers, and is what the mirror's project
is given. The chip carries no serial number, so that path is stable only
while it is the only CH340 on the box.

Only the mirror opens the device. Everything else — the `dccex` translator,
JMRI, hand-held throttles — is a client of 2560, and they coexist: every byte
the command station sends reaches every client, and a client's bytes go to it
only as whole `<…>` messages (ADR-0043). The translator reaches that port at
`host.docker.internal`, the box from inside its container, and
`TC49_STATION` names another machine where the station hangs off one.

**This railroad's per-district trip currents live on the box**, in
`/etc/rails49/dccex-startup.txt`, and nowhere else: a district is a hardware fact
that reaches no bus topic and no document
([#217](https://github.com/rails49/control/issues/217)). The `dccex` service
is given it with `--startup` and the file itself is mounted read-only —
**the file, not `/etc/rails49`**, which also holds the door's `acme.env`, so
a directory mount would hand the translator this box's one secret. What may go in it is
[dccex/README.md](dccex/README.md#the-startup-file); it is sent on every
power-on and on nothing else, and a station whose limits are compiled into
its firmware needs none of it.

An empty file is an ordinary state, and a box with no values to set deploys
and runs on the limits its firmware was built with (ADR-0050). It is made
empty rather than left out, because a bind mount whose source is missing is
created by the daemon as a root-owned *directory* and the translator would
then open a directory as its startup file — the fault `~/tc49` had (#387).
`scripts/deploy.sh` makes it where this account can write `/etc/rails49`, and
says what to run by hand where it cannot rather than stopping the deploy over
a file that is allowed to be empty. What it says to run is the line above,
and it removes what is at the path first: against a directory `install`
writes a file called `null` inside it and reports success, leaving the
directory there for the translator to open
([#529](https://github.com/rails49/control/issues/529)).

**Edit it in place.** A single-file bind mount binds the inode, so an editor
that replaces the file leaves the container reading the values it was created
with — the fault the old proxy had, going on serving the route table it
started with while `git pull` replaced the file under it
([#353](https://github.com/rails49/control/issues/353)). The directory mount
that cured that one is not available here. A container that has lost the file
this way is recreated:

```
docker compose --env-file /etc/rails49/box.env \
  --env-file /etc/rails49/deploy.env -f deploy/compose.yaml \
  up -d --force-recreate --no-deps dccex
```

Then power the railroad off and on: the file is read at that transition, so
the edit and the power cycle together are the whole of changing a limit.

### JMRI

An operator's tool and none of this repository's business. It used to be a
service in the file below, which made it part of a railroad's stack that it
never was; it is a compose project of its own in the installation now, started
and stopped without touching anything here
([rails49/installation ADR-0002](https://github.com/rails49/installation/blob/main/docs/adr/0002-jmri-is-a-compose-project-of-its-own.md)),
and that repository's README is where the command sits.

It publishes no port. noVNC answers at `https://jmri.gleis49.org`, behind the
same door as everything else, and the image does not start JMRI: open that
name and click DecoderPro or PanelPro on the desktop.

What is `control`'s here is the one thing JMRI talks to: the command station,
as a plain client of `dccex-usb` on 2560 over the LAN, like any hand-held
throttle (ADR-0043). Its connection is a DCC++ over TCP one, and the host in
it is the box rather than a compose service name now that JMRI is in another
project — set it in DecoderPro once and save. The rest of what is configured
through the GUI lives in a volume of that project's
([#299](https://github.com/rails49/control/issues/299) is the last time that
volume needed a click here).

### The router

Most home routers strip private addresses out of answers from upstream DNS —
DNS rebind protection, and it is the one thing that can break this design. A
FritzBox has it under **Home Network → Network**, the **Network Settings**
tab, at the foot of the page behind the **Change Advanced Network Settings**
button, on its **DNS Rebind Protection** tab, where `gleis49.org` goes
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

## What the containers declare

The three containers a browser reaches — the built ui, the store and the
broker — carry their own routers as labels on themselves
([#556](https://github.com/rails49/control/issues/556)). What reads them is
the door: one reverse proxy per box, the installation's rather than this
repository's, in front of every stack on the box, taking its routers off
containers rather than out of a file. A UI's paths then change in the same
commit as the UI, and this repository stops owning the routing for UIs it does
not build.

| container | router | what it claims |
| --- | --- | --- |
| `web` | `tc49-app` | the bare host: everything no other router claims |
| `store` | `tc49-store` | `/backup`, `/drawings`, `/review`, `/layouts`, `/rosters`, `/catalogue`, on `:8765` |
| `broker` | `tc49-mqtt` | `/mqtt`, prefix stripped, to the WebSocket listener on `:9001` |
| `broker` | `tc49-mqtt-foreign` | the same from a page on another origin, answered 403 |

The names are keyed to the stack rather than to the site. The door sees every
stack on the box, so a name has to be unique across all of them, and the site
prefix named a route directory that no longer exists.

**The name comes from the box's declaration.** `/etc/rails49/box.env` holds
`BOX_DOMAIN`, the name the box is reached at, and every stack on the box is
started against that one file, so this UI is at `control.$BOX_DOMAIN` and
naming a box is editing a file on the box rather than forking this repository.
No template is rendered and no file is copied — compose substitutes it. A box
with no declaration yet gets a blank name, and compose says which variable is
missing.

**Each router states its priority.** Traefik's default is the rule's length,
which was legible while every rule sat in one file and is not now that they
sit on three containers: the app's rule is the bare host and matches every
path under it, so the store's, the bus's and the refusal's each say outright
that they come first. The refusal's precedence over the bus router it stands
in front of is what this exists to keep, and nothing shows a reader that
shortening one rule changes what another matches.

**The refusal compares origins whole.** The route file matched a pattern with
the dots in the name escaped; the name now comes from the declaration and a
dot inside it cannot be escaped on its way into one, and
`control.gleis49.org` as a pattern admits `control-gleis49.org`, which
somebody may register. So the two origins that are the app's own — `https://`
and `http://`, TLS terminating at the door — are named exactly, and anything
else carrying an `Origin` is refused. A handshake with no `Origin` is a native
client and still goes through.

The pattern also admitted the app's own name with a port after it. That is
dropped rather than written out twice more: the door listens on 443 and 80,
and a browser leaves a scheme's default port out of `Origin`, so no page the
door serves sends one.

**Only what the door reaches joins the shared network.** `web`, `store` and
`broker` join `rails49`, the network the installation creates and every stack
on the box shares; `scheduler`, `dispatcher`, `driver`, the layout interface,
the simulator and the translators stay on this stack's own network, because
they talk to the bus and not to browsers. Each of the three is on two networks
and names the shared one again in a label, or the docker provider picks
whichever container address it finds first. That is
[ADR-0001](https://github.com/rails49/installation/blob/main/docs/adr/0001-only-what-the-door-reaches-joins-the-shared-network.md)
in `rails49/installation`.

The network is the installation's to create, and compose declares it external
here, so a box that has not installed the installation is told so rather than
quietly making a network of its own:

```
network rails49 declared as external, but could not be found
```

**`/mqtt` is on the app's own origin** because a page served over TLS cannot
open a `ws://` socket, and the browser refuses it rather than warning. The run
view is a client of the broker like any other app
([ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
decision 4), and native clients go straight to 1883 and never come through the
door. In development vite proxies the same paths, so the app builds one URL out
of the page's own on both.

| path | development | the layout box |
| --- | --- | --- |
| `/mqtt` | the broker container's websocket listener on `:9001` | the same, as the `broker` container |
| `/backup`, `/drawings`, `/review`, `/layouts`, `/rosters`, `/catalogue` | vite's own proxy to the store | the store, `:8765` |
| everything else | vite, `:5173` | `ui/dist` through nginx |

**A handshake from a page on another origin is answered 403 before the
upgrade**, so a foreign page gets no socket at all. A WebSocket has no
preflight, so this is the whole of what stands between a page somebody's
browser visits and the gestures a client may publish
([ADR-0056](adr/0056-the-browsers-way-onto-the-bus-refuses-a-foreign-origin.md),
[#349](https://github.com/rails49/control/issues/349)). Mosquitto has no
`Origin` setting, so the rule is stated in front of it rather than in an app,
`lib/origin.py` being the same rule at the store's face. A handshake with no
`Origin` is a native client and goes through, and one on 1883 does not pass
this way at all.

The built UI needs nginx behind the door because the door proxies and does not
read files. That is the whole of what `web` is.

## When it does not work

**`network rails49 declared as external, but could not be found`** — the
installation is not up on this box. It creates that network, and every stack
that serves a UI joins it.

**Compose stops on an unset `BOX_DOMAIN`** — it was run without
`--env-file /etc/rails49/box.env`. The message names the variable it wanted.

**`https://control.gleis49.org` answers 404** — the door is up and this stack
is not, or its containers are not on the shared network. `docker compose
--env-file /etc/rails49/box.env --env-file /etc/rails49/deploy.env -f
deploy/compose.yaml ps` says which.

**The name resolves to nothing, or to `0.0.0.0`** — DNS rebind protection at
the router, above. `dig control.gleis49.org @1.1.1.1` answers correctly while
the router does not, which is how to tell this apart from a wrong record.

**No certificate, or the door's log says a challenge failed** — the
installation's, not this stack's: its README is where the credential and the
provider are written.

**The internet is down mid-run** — a `hosts` line covers the operating
console, and a phone cannot have one, so hand-held throttles are off the
layout until the name resolves again. A long TTL on the record is the whole
mitigation.
