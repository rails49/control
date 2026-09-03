# The bus is a broker, each app is its own process, and the bridge is deleted

Resolves [#173](https://github.com/rails49/control/issues/173).
[ADR-0008](0008-bus-contract-is-the-mqtt-safe-intersection.md) fixed the bus
contract as what MQTT also promises,
[ADR-0013](0013-apps-are-deployment-units.md) made an app a unit that runs as
its own container, and every page since has called the in-process bus and the
WebSocket bridge milestone bindings to be replaced. #173 held the replacement
behind the first train moving on hardware. This lifts that gate, answers the
two questions #173 left open, and states what the switch changes in the
contract.

## Why the gate is lifted

#173 waited for hardware to answer "whether the translator wants its own
process, and what latency turns out to matter". The first is not a
measurement: ADR-0013 says every app is its own process, by rule, and a
translator is an app. The second is real, but waiting cannot answer it. Only
running on the broker can.

What forces the switch is that the in-process bus is a process boundary.
Hardware built to speak the bus
([ADR-0058](0058-hardware-meets-the-bus-and-a-translator-is-only-for-hardware-that-cannot.md))
connects to the broker and finds nothing of ours there, because every app
publishes into a Python queue inside one process. The design says such
hardware is a participant like any other; the binding made that impossible.
The deployment then put five apps in one container (#354), which
[ADR-0042](0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)
had said would contradict ADR-0013, and did.

## Decisions

**1. The deployed apps run on an MQTT binding of the bus, and the in-process
binding stays for the harness.** `lib` gains a second binding of the same
interface — subscribe, publish, drain — over a broker. State topics are
published retained and event topics are not; `at` is stamped from wall time,
since processes on a broker share no run clock. The client's network thread
appends to a queue and the app's own loop drains it, so every app keeps its
single thread and none of its code changes. `bench`, `sweep` and the property
suite keep the in-process binding: byte-identical replay is what they exist
for, and [ARCHITECTURE.md](../ARCHITECTURE.md#tests) already says determinism
is a property of that binding and not of the system. Question 1 of #173:
both bindings survive, each for one use.

**2. One railroad per broker, chosen at start.** Topics stay flat. Every app
process is given the railroad's name when it starts, and the running binding
of the layout interface publishes it on a retained state topic so a view can
read which railroad it is looking at. Switching railroads is restarting the
apps, and the band's railroad picker goes with the bridge. Question 4 of
#173 is answered. A namespace level per railroad is rejected: it would touch
every filter in the inventory for a case this deployment does not have, and a
shared broker can add a prefix in front of `tc49/` at its own edge
(Mosquitto's bridge does exactly this) without the contract changing.

**Amended under
[ADR-0060](0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md):**
"switching railroads is restarting the apps, and the band's railroad picker
goes with the bridge" no longer holds. A railroad is chosen on the bus —
`tc49/layout/railroad_wanted`, answered by the layout interface — and the
picker stays and writes it, live only while track power reads `off`. That
clause did not engage with ADR-0038, which had considered restricting the
picker and declined, and taken literally it leaves a person unable to create a
railroad from the app at all. Loading one clears the retained rows each app
owns, which restarting the apps does not. The rest of this decision is
untouched: one broker runs one railroad, topics stay flat, and a namespace
level per railroad is still rejected.

**3. Retained state lives in the broker and nowhere else.** `durable.py`,
`tc49 live --state` and the state file are deleted. The broker keeps retained
values while it runs, which is what restarting one app needs, and keeps
nothing across its own restart (`persistence false` in
`deploy/mosquitto.conf`), so a power cut is the railroad coming up at rest,
which [ADR-0054](0054-the-railroad-comes-up-at-rest-and-points-replay.md)
already requires.

**4. The bridge is deleted and the browser is a client of the broker.** The
run view speaks MQTT over WebSocket to the broker's own listener, through the
proxy as `/mqtt`. The origin rule of
[ADR-0056](0056-the-browsers-way-onto-the-bus-refuses-a-foreign-origin.md)
moves in front of the broker as a proxy middleware
([#349](https://github.com/rails49/control/issues/349)) and lands in the same
change as the deletion. What the bridge enforced beyond origin — that a
browser publishes only the browser-writable rows — becomes convention: with
anonymous clients a broker cannot tell a page from an app, and ADR-0042
already says anyone on the LAN may drive. The ACL of
[ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)
stays derivable from the inventory and is not built.

**5. Every app comes up alone.** Each app has a command line and a container
of its own. Started against an empty broker with nothing else running, it
connects, publishes its own retained rows and stays up. One that needs the
railroad's documents reads them from the store's HTTP face and retries until
the store answers, as the translator retries the mirror. No `depends_on`
anywhere in compose. The hardware a box owns is that box's choice and lives
in a profile of its own ([#357](https://github.com/rails49/control/issues/357)).
The `session` container and `tc49 live` go. Hardware needs no layout: it
reads the wanted rows and writes what it observes, and it does not know that
layouts exist.

**6. A point or signal address carries no system level.**
`wanted/point/<addr>`, `wanted/signal/<addr>`, `device/point/<addr>`. The
address is the string the drawing carries and the hardware answers to.
Whatever is wired subscribes the wanted rows and acts on the addresses it
recognises, as traction already does, and the drawing's refusal of an
address that names no system goes. The system level of
[ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)
is withdrawn: it put a product's name into the contract, and what it was for
— several systems on one railroad — holds without it, an address nobody
answers to doing no harm. The cost is the deployer's: two systems that number
a point alike both act.

**7. The link row is keyed by an arbitrary id.** `device/link/<id>`, where
the id is whatever the publisher calls itself, appearing in no drawing, no
configuration and no list of ours. The row keeps its job: it is where a
participant that knows it cannot reach its hardware says so
([ADR-0050](0050-broken-hardware-is-reported-never-worked-around.md)), and
it needs a key because one railroad may have several participants and the
second's `up` would otherwise erase the first's `down`. The layout interface
folds `state/power` to `off` for any id it has heard say `down` and never
waits for one it has not heard, which keeps ADR-0058: nothing must announce
itself. A publisher may set an MQTT last will on its row, which
[ADR-0040](0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md)
permits as a faster signal that no safety property depends on.
`device/track` gains an optional free-text `reason`, as the sensor row has,
so the participant that reports the supply can say why it is off.

## Amendments

- ADR-0042, "the five apps stay native until MQTT lands": MQTT lands now,
  and the apps containerize with it.
- ADR-0043: the system level of an address and "a translator subscribes its
  own system" are withdrawn (decision 6). The rest stands.
- ADR-0058, "`tc49 live --station` is scaffolding": the scaffolding is
  removed (decision 5).
- ADR-0032, ADR-0040, ADR-0050, ADR-0054 are unchanged; each is cited above
  as holding on the broker.

## Rejected

- **Keeping the bridge on top of the broker** as the browser's way in. It
  would be a second copy of what the broker's WebSocket listener does.
- **A namespace level per railroad** (decision 2).
- **A per-client ACL.** It needs client identities, which need credentials,
  which ADR-0042 keeps off the safety path.
- **Dropping the link row.** A participant that does not report the supply
  would then have no way to report a failure it knows about, against
  ADR-0050 (decision 7).
- **Waiting for the first train** (#173's gate). The transport does not
  depend on a railroad, and the hardware that is waiting to be attached
  cannot be attached without it.

## Consequences

The work, each an issue, in the order the dependencies allow:

- [#367](https://github.com/rails49/control/issues/367) the address grammar
  (decision 6) and
  [#368](https://github.com/rails49/control/issues/368) the link row and the
  supply's reason (decision 7): the contract, first.
- [#369](https://github.com/rails49/control/issues/369) the MQTT binding in
  `lib` (decision 1).
- [#370](https://github.com/rails49/control/issues/370) `GET /layouts/<name>`
  and the store client in `lib`, and
  [#371](https://github.com/rails49/control/issues/371) the railroad's name
  on the bus (decision 2).
- [#373](https://github.com/rails49/control/issues/373)–[#378](https://github.com/rails49/control/issues/378)
  a command line and a container for the scheduler, dispatcher, driver,
  layout, simulator and `dccex`;
  [#379](https://github.com/rails49/control/issues/379) the typed readings as
  a client (decision 5).
- [#357](https://github.com/rails49/control/issues/357) compose: one service
  per app, no `depends_on`, hardware in its own profile.
- [#380](https://github.com/rails49/control/issues/380) the run view as a
  client of the broker (decision 4).
- [#381](https://github.com/rails49/control/issues/381) delete the bridge,
  the session and the durable file, with the origin middleware of #349
  (decisions 3 and 4).
- [#372](https://github.com/rails49/control/issues/372) a cold start per app
  and a compose check, in the gate.
- [#382](https://github.com/rails49/control/issues/382) the docs.

[#123](https://github.com/rails49/control/issues/123) is decided as far as
decision 3 reaches: a restart of one app keeps its state because the broker
holds it, and a power cut comes up at rest. The `jmri` translator of
[#360](https://github.com/rails49/control/issues/360) is a container of its
own under decision 5, keyed by its own id under decision 7.
