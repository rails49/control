# A browser is not on the LAN, and the store refuses it

**Amended by [ADR-0059](0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md), 2026-09-03:** "the bridge is not covered" below is settled and the face it names is gone. ADR-0056 extended this rule to the browser's way onto the bus, and with the bridge deleted that way is the broker's WebSocket listener, where the rule stands in front of it as a proxy middleware on `/mqtt` rather than in an app.

> **Two things in the paragraph headed "No client we serve loses anything"
> are wrong.** Its premise — "in development vite proxies the store's routes
> without rewriting the header" — is false: vite does rewrite it, and every
> browser write to the store was refused until
> [ADR-0057](0057-one-origin-rule-and-both-faces-read-it.md) fixed the proxy
> and moved the rule into `lib`. Its route list is also short by one:
> [#341](https://github.com/rails49/control/issues/341) proxies `/backup`
> alongside `/drawings`, `/review` and `/rosters`, which matters because
> `POST /backup/restore` is the request this ADR reasons about nine lines
> above and could not reach the store through either proxy when this was
> written ([#346](https://github.com/rails49/control/issues/346)).
>
> The decision stands and nothing here is superseded. That paragraph's
> supporting sentences do not.

Resolves [#329](https://github.com/rails49/control/issues/329).
[ADR-0042](0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)
rules that there is no authentication and the LAN is the trust boundary:
anyone on the wireless may open the run view, drive a train, and overwrite a
drawing. That ruling stands. What this one says is that the store's HTTP face
was not enforcing it — it was wider.

## What was wider

Every route answered with `Access-Control-Allow-Origin: *`, and `OPTIONS`
approved every preflight. So a page on any origin at all, opened in a browser
on a laptop that happens to be on the same network, could read `GET /backup` —
which answers the backup history — and send `POST /backup/restore` with a
commit taken from it. The page's author is not in the room and was not
invited. They do not need to be on the LAN; they need somebody who is to open
a tab.

That is a different boundary from the one ADR-0042 argued for. The argument
there is about *the people present* — "a login between a person and a throttle
buys nothing on a layout where the people present are the people invited" —
and it is sound about people. A browser is not a person on the LAN. It is a
program that runs whatever the page it loaded tells it to, against every
address it can reach, on behalf of somebody who is nowhere near the railroad.

## The store refuses a request that came from another origin

A request carrying an `Origin` header that is not this server's own `Host` is
answered 403 and nothing runs. No `Access-Control-*` header is sent on any
reply.

`Origin` is written by the browser and a page cannot forge it, so this is a
check with teeth rather than a convention. Refusing on the header rather than
merely withholding the CORS reply is what makes it cover writes as well as
reads: dropping `Access-Control-Allow-Origin` alone would stop a page reading
an answer, and a `POST /backup/restore` sent as `text/plain` needs no
preflight and would still have run, blind.

The comparison is host against host and not scheme against scheme, because TLS
terminates at the proxy (ADR-0042): the browser's origin is
`https://layout.rails49.org` and what arrives at the store is plain HTTP under
that same `Host`.

**No client we serve loses anything.** The app fetches these routes on its own
origin — vite proxies `/drawings`, `/review` and `/rosters` in development, and
the same proxy that serves the page routes them on a layout server — so the
browser sends no cross-origin request and never needed a CORS header. The
comment in the code claiming otherwise ("the editor is served from its own
origin in development, so the browser asks") was describing an arrangement
that no longer existed, and its second half ("bound to the loopback, there is
nobody else to ask") stopped being true when ADR-0042 gave the apps a bind
address.

**A request with no `Origin` goes through.** A native client, `curl`, a
same-origin `GET`: no page wrote the header, because no page is involved. The
LAN boundary is exactly where ADR-0042 put it, and this narrows nothing about
it. Somebody on the wireless can still drive the store from a terminal, which
is the decision ADR-0042 made and is not reopened here.

## What was not chosen

**Authenticating operators** remains rejected for ADR-0042's reason, unchanged:
the answer to "who is on the network" is still "the people in the room". This
ADR does not put a login anywhere.

**Writing the boundary down and changing nothing** was the other candidate the
issue named. It loses on cost: the fix is a header comparison, it breaks no
client, and the paragraph would have had to say that a page anywhere on the
internet may roll the store back, which is not a boundary anybody chose.

## Consequences

The rule belongs to the whole face and not to `/backup`. It was found on the
backup routes, where the blast radius is the largest — rolling the store back
rather than overwriting one drawing — but `PUT /drawings/<name>` was reachable
the same way and is covered by the same check.

A future browser client on a genuinely different origin would need an
allowlist here. There is none today and adding one before there is a client
would be inventing a policy for nobody.

The bridge is not covered. `tc49 live`'s WebSocket is a separate face with a
separate handshake, and a page can open a WebSocket cross-origin with no
preflight at all. Whether it gets the same check is
[#342](https://github.com/rails49/control/issues/342) and is not decided here.
