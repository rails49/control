# One origin rule, and both faces read it

Resolves [#351](https://github.com/rails49/control/issues/351).
[ADR-0055](0055-a-browser-is-not-on-the-lan-and-the-store-refuses-it.md) made
the store refuse a page on another origin and
[ADR-0056](0056-the-browsers-way-onto-the-bus-refuses-a-foreign-origin.md) made
the bridge do the same, one clause wider. Two faces, two copies of a check,
and they disagreed. This says there is one rule, in one place, and both read
it.

## What was wrong

ADR-0055 rested on a premise that is false:

> In development vite proxies the store's routes without rewriting the header,
> so the two agree there for the same reason.

Vite rewrites it. `ui/vite.config.ts` named the four store routes as bare
strings, and vite turns a string shorthand into `changeOrigin: true`, which
replaces `Host` with the proxy's target. So the store compared
`Origin: http://localhost:5173` against `Host: 127.0.0.1:8765` and refused.

**Every browser write to the store was refused for four hours and nobody
noticed**, which is the part worth keeping. A browser omits `Origin` on a
same-origin `GET` and sends it on a same-origin `POST` or `PUT`, so the reads
went on working and only the writes failed. The app came up, listed the
drawings, and would not save one. A check that fails this way does not
announce itself.

The bridge was not affected, and only by luck: ADR-0056 had given it a
loopback clause a few hours earlier, for `?bridge=`, and that clause covers
the rewritten host as well.

## One rule, in `lib`

`lib/origin.py` holds the whole of it, and the store's `_same_origin` and the
bridge's `_refuse_foreign` both call it:

- no `Origin` — a native client, a `curl`, a same-origin `GET` — goes through;
- an `Origin` whose host equals the request's own `Host` goes through;
- an `Origin` whose hostname is `localhost`, `127.0.0.1` or `::1` goes
  through, whatever the `Host`;
- anything else is refused, 403 at the store's routes and 403 before the
  upgrade at the bridge's handshake.

That is ADR-0056's rule verbatim. What changes is that the store now reads it
too, and that neither app states it.

**Why the loopback clause belongs on the store as well**, when the proxy fix
below already makes development agree without it: because the alternative is
two rules for one boundary, and because this failure was invisible. A page
served from this machine reaching a face on another port of it is the same
situation at both faces — `?bridge=` at one, a proxy that rewrote `Host` at
the other — and the argument that admits it is the same argument. ADR-0056
made it in full: a page an attacker controls is served from somewhere else and
its origin is that somewhere, so none can claim loopback, and anyone who can
serve a page from this machine can reach either face with no browser at all.

## And the premise is fixed rather than relied on

`ui/vite.config.ts` now gives each store route `changeOrigin: false`, so
`Host` arrives as the page sent it and the host comparison covers development
on its own. The reverse proxy in front of a layout server already passes the
header through, so this is what makes development behave the way deployment
does rather than lean on the clause above.

Both, not either. The proxy fix is what makes the two environments alike; the
loopback clause is what keeps the next proxy that rewrites a header from
silently breaking writes again.

## What was not chosen

**Fixing vite and leaving the store's rule alone** was the smaller change. It
loses on the two things that made this bad: the faces would still hold
different rules for one boundary, and the failure mode would still be a silent
partial one that a `GET`-only smoke test passes.

**Widening to the private ranges** stays rejected on ADR-0056's reasoning,
unchanged.

**Editing ADR-0055 to say the opposite of what it says** is not how the
sequence records anything. Its text stands as the decision it was, with a note
at the top pointing here.

## Consequences

The rule is one function, and a face that grows later reads it rather than
writing a third copy. Where it cannot — mosquitto, when the bridge is deleted,
has no `Origin` setting — the rule is satisfied at the proxy instead
([#349](https://github.com/rails49/control/issues/349)).

A test that reaches a face over loopback proves the loopback clause and not
the host comparison. `tests/store/test_server.py` names a host to exercise the
comparison on purpose; anything testing this later has to do the same or it
proves nothing.
