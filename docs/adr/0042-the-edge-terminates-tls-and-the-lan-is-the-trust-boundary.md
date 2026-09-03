# The edge terminates TLS and the LAN is the trust boundary

**Amended by [ADR-0059](0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md), 2026-09-03:** "the five apps stay native until MQTT lands" below is superseded. MQTT lands, and the apps containerize with it, one service each.

The stack is reached at one name over a real certificate, and behind that name
every app listens in plaintext on loopback. One reverse proxy holds the
certificate and owns the only socket anyone off the box can reach. Nothing
inside the stack speaks TLS, and nothing on the LAN is asked who it is.

Three rulings, which are one argument seen from three sides.

## TLS terminates at the edge

Dispatcher to broker to driver stays plaintext. Those bytes never leave the
machine, so there is nothing on the wire to protect, and the authorization
that does matter is the broker ACL
([ADR-0035](0035-a-topic-has-one-writing-role.md)), which works exactly as
well over plaintext.

What mTLS would add is a certificate rotation on the most safety-critical path
in the system. A grant that does not arrive because a certificate expired is a
train that does not stop, and the physical railroad decides
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)): a
failure mode that can only strand a train is worse than an eavesdropper who
would have to already be inside the box.

The certificate itself is obtained over DNS-01, which proves control of the
name by writing a TXT record. No inbound connection is involved at any point,
so no port is forwarded and no router is configured. The name resolves to a
private address in public DNS: anyone may look it up, and it only works on the
LAN.

## The LAN is the trust boundary

There is no authentication anywhere. Anyone on the wireless can open the run
view, drive a train, and overwrite a drawing through `PUT /drawings/<name>`.

That is the decision rather than an oversight. An operator walks up with a
phone and starts running trains, and a login between a person and a throttle
buys nothing on a layout where the people present are the people invited. The
cost is bounded on both sides: `bench/layouts/` is committed, so a bad write is a
checkout, and there is no inbound path from the internet to abuse.

What this does not license is reading the ACL as a guard against strangers. It
separates *roles*, not people: it stops the driver writing what the dispatcher
writes. It was never what keeps an uninvited client out, and the broker work
must not be designed as though it were.

## Infrastructure containerizes now, the apps last

[ADR-0013](0013-apps-are-deployment-units.md) makes an *app* a deployment
unit. A reverse proxy and a broker are not apps: they are third-party
infrastructure that no `src/tc49/` package owns, and putting them in
containers puts nothing of ours in one.

So the ordering argued for the apps — native, then MQTT, then containers,
because containerizing first would put five apps in one container — does not
reach them. The proxy runs as a container from the day it appears and the
broker will too, while the five apps stay native until MQTT lands. Containers
are also how the proxy avoids being installed: the image is stock, and nothing
is built or left on the machine.

## The alternatives

**A local DNS server**, handing out the name on the LAN, was rejected on the
ground that the resolver becomes a single point of failure for the internet
and not merely for the railroad. This design runs none.

**A tunnel** through a public edge routes latency-critical traffic through
somebody else's network. It could later serve remote *viewing* of the UI, and
never the dispatcher-to-driver path.

**mDNS or bare addresses** cost nothing and give no certificate, so the
browser has no secure context and `getUserMedia` and its neighbours stay
unavailable. That is the whole reason a real name is worth having at all.

**Authenticating operators** was considered and is one Traefik directive away
if it is ever wanted. It is not wanted while the answer to "who is on the
network" is "the people in the room".

## Consequences

The names and the address are public. Every certificate is published in the
Certificate Transparency logs, so the names are enumerable by anyone, and the
private address is in public DNS by design. Traffic stays on the LAN; the
facts about it do not.

Name resolution becomes an internet dependency. A `hosts` line covers the
machine that has one, and a phone cannot have one, so an outage at the wrong
moment takes the hand-held throttles off the layout. A long record TTL is the
only mitigation and it is a partial one.

The apps grow a bind address. Loopback was the authorization until now, and a
proxy in a container cannot reach loopback on a macOS host, so `tc49 serve`
and `tc49 live` take `--host`, defaulting to `127.0.0.1` and set wider by
`scripts/dev.sh`. When the apps containerize they need it anyway.

This belongs to the end state of [GOALS.md](../GOALS.md) — a layout server
with operators on their own phones — and is landed early because it is cheap
and gated on nothing. The deployment itself lives in [deploy/](../../deploy)
and is described in [DEPLOY.md](../DEPLOY.md).
