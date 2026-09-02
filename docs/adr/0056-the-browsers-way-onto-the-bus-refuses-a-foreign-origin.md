# The browser's way onto the bus refuses a foreign origin

Resolves [#342](https://github.com/rails49/control/issues/342).
[ADR-0055](0055-a-browser-is-not-on-the-lan-and-the-store-refuses-it.md) made
the store's HTTP face refuse a page on another origin, and scoped itself
there: the bridge has a different handshake and the answer might have
differed. It does not. This ADR extends the same rule to the other face a
browser can reach, and states it in terms that outlive the file enforcing it
today.

## What is wider

`tc49 live`'s bridge (`src/tc49/lib/bridge.py`) accepts every handshake. It
reads the socket path to learn which railroad a client wants and consults no
header. A WebSocket is not subject to the same-origin policy at all — there is
no preflight, and the browser opens the socket whatever the origin — so the
`Access-Control-*` question that ADR-0055 turned on never arises here. A page
on any origin, opened in a browser on a laptop that happens to be on the
layout's network, gets a socket.

What that reaches is larger than the store's. The relay publishes a frame on
any topic the inventory marks `browser=True`, which is eight gestures:
`power_wanted`, `mode_wanted`, `throttle_wanted`, `request_wanted`,
`reversal_wanted`, `run_wanted`, `placement_wanted` and `cancel_wanted`. A
page could cut track power or open a throttle on a running railroad. The read
side is not smaller: on join a client is sent the last value of every state
topic and then every `tc49/#` event, which is the whole picture of the run.

## The browser's way onto the bus refuses a foreign origin

A WebSocket handshake carrying an `Origin` header is answered **403 before the
upgrade** — no socket, no handler thread, no frame — unless either

- the origin's host equals the handshake's own `Host`, or
- the origin's hostname is `localhost`, `127.0.0.1` or `::1`.

A handshake carrying **no `Origin`** goes through.

`Origin` is written by the browser and a page cannot forge it, so this is a
check with teeth rather than a convention. The comparison is host against host
and not scheme against scheme, for ADR-0055's reason: TLS terminates at the
proxy, so the browser's origin is `https://layout.rails49.org` and what
arrives at the bridge is a plain handshake under that same `Host`. In
development vite proxies `/live` without rewriting the header, so the two
agree there too.

**Refused before the upgrade rather than in words.** Every other refusal the
bridge makes — a railroad it is not running, a topic that is not inbound —
is an `{"error": …}` frame over an open socket, because those are refusals to
a client we serve. This one is not. Handing a foreign page a socket in order
to tell it that it may not have one contradicts the decision; the page gets a
failed connection and learns nothing. No client we serve can reach this path,
so nothing loses a diagnostic.

**A handshake with no `Origin` is a native client.** `curl`, a native
throttle, the bench's own test client: no page wrote the header because no
page is involved. Somebody on the wireless can still drive the bus from a
terminal, which is the decision
[ADR-0042](0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)
made and is not reopened here.

### The loopback exception, and why it costs nothing

The panel accepts `?bridge=ws://127.0.0.1:8766` — the whole of the browser's
configuration, naming a session somewhere else
([#148](https://github.com/rails49/control/issues/148),
`ui/src/ui/tc-panel.ts`). That is a page on `localhost:5173` opening a socket
to a different host, and the first clause alone would refuse it. Unlike
ADR-0055, this rule does break a client we serve, so it carries the exception
that keeps it working.

The exception is provably no weaker than the rule. The page this defends
against is served from somewhere else on the internet, and its origin is that
somewhere: a foreign origin is never loopback, and no page an attacker
controls can claim one. What the exception admits is a page served from the
machine the bridge runs on, and anyone who can serve a page from there can
reach the bus directly with no browser at all.

It stays at loopback and does not widen to the private ranges. Testing on a
phone is already served by pointing `dev` at the box's LAN address and going
through the proxy (`docs/DEPLOY.md`, `scripts/dns.sh`), where page and bridge
arrive under one host and the first clause covers it. Widening would buy
`?bridge=` typed on a phone, and would cost the rule its one sentence: three
CIDR ranges and IPv6 unique-local, and a reader who has to work out whether an
address is private before knowing whether the railroad is protected.

## What was not chosen

**Relaying to a foreign page but refusing its writes** was the narrower shape.
It loses on the argument ADR-0055 actually makes: a foreign page is refused
because its author is not in the room, and hearing every block's occupancy,
every train's speed and every point's position is not a lesser thing to hand
someone than a throttle. It also costs more — two rules where one does, and a
second place for the browser mark to be got wrong.

**Writing the boundary down and changing nothing** loses for the same reason
it lost in ADR-0055, and by more: the fix is a header comparison, and the
paragraph would have had to say that a page anywhere on the internet may cut
power to a running railroad.

**A configured allowlist**, or a `--allow-origin` flag, is the general form of
the loopback exception. It buys generality nobody has asked for and puts a
security decision in a command-line argument, where an installation can get it
wrong. ADR-0055 declined to invent an allowlist for nobody; there is now
exactly one client, and one clause serves it.

**Authenticating operators** remains rejected for ADR-0042's reason,
unchanged.

## Consequences

**The rule belongs to the face and not to the file.** The bridge is a
milestone binding that gets deleted: when the bus becomes a real broker the
browser speaks MQTT over WebSocket to mosquitto directly (ADR-0013 wiring
note, [#67](https://github.com/rails49/control/issues/67)). Mosquitto has no
`Origin` setting, so the broker satisfies this rule at the proxy — a Traefik
middleware on `/mqtt` — rather than in the app. That is
[#349](https://github.com/rails49/control/issues/349), filed rather than left
in prose, because prose is how #342 came to be rediscovered.

**Two faces, and now both refuse.** A browser can reach the store's HTTP
server (ADR-0055) and the bridge (here), and nothing else: `dccex_usb`'s
station mirror is a raw TCP server, which no page can open a socket to. The
boundary is whole until the broker arrives.

**`?bridge=` is loopback-only from here on.** It was already development-only
in practice — a page served over TLS cannot open a plain `ws://` at all — and
that is now a rule rather than an accident.
