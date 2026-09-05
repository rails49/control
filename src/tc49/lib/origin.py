"""Whether a browser request came from the page the server is part of.

One rule, read at the store's HTTP routes: the face a browser reaches that is
ours to check. The browser's other way in is the broker's WebSocket listener,
where the same rule is stated as a proxy middleware on `/mqtt` rather than in
an app — Mosquitto has no `Origin` setting (ADR-0056, ADR-0059 decision 4) —
so the rule stays here, written once, however many faces read it (ADR-0055,
ADR-0057).

`Origin` is written by the browser and a page cannot forge it, which is what
makes this a check rather than a convention. It is absent exactly where there
is no page — a native throttle, a `curl`, a same-origin `GET`, which browsers
send without one — and those go through: the LAN is the trust boundary and
this narrows nothing about it (ADR-0042).
"""

from urllib.parse import urlsplit

LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
"""Where a page served from this machine is at. A page an attacker controls is
served from somewhere else and its origin is that somewhere, so none can claim
one of these — which is what makes admitting them free."""


def is_own_page(origin: str | None, host: str | None) -> bool:
    """Whether a request carrying this `Origin` and `Host` is the app's own.

    Host against host and not scheme against scheme, because TLS terminates at
    the proxy: the browser's origin is `https://layout.rails49.org` and what
    arrives is plain HTTP under that same `Host` (ADR-0042).

    A loopback origin is admitted whatever the `Host`, because a page served
    from this machine reaches a face on another port of it, and the ports are
    not one origin: a proxy that rewrites `Host` to the target — which vite
    did for the store's routes until #351 — leaves the two disagreeing.
    Anyone who can serve a page from here can reach the face with no browser
    at all, so the clause gives away nothing the machine did not already have
    (ADR-0057).
    """
    if origin is None:
        return True
    at = urlsplit(origin)
    return at.hostname in LOOPBACK or at.netloc == (host or "")
