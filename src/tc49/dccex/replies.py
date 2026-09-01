"""What the station says, and the two facts this app reads out of it.

The station writes `<…>` messages to every client, replies and unasked
broadcasts alike, and one byte stream cannot say which a line is — `station`
fans the whole conversation to everybody and routes nothing (ADR-0043). So
what arrives here is everything the station has to say to anyone, and the
reading is deliberately narrow: the power each track is in, and whether the
emergency-stop lock is on. Everything else — a slot's speed, a turnout the
station keeps of its own, a sensor it polls, a fast clock — is another
client's business and is passed over unread.

Two functions, both pure. `messages` is the framing rule, bytes in and whole
messages out; `reply` is one message read into a fact or into `None`. Neither
raises, and a message this app does not recognise is not an error: it is the
ordinary case, most of the traffic on the port being somebody else's.

`station` frames the same `<…>` delimiters and this is not shared with it.
Apps import `tc49.lib` and themselves, never each other (ADR-0013), and the
delimiters are the hardware's rather than a contract of ours — `station`
mirrors a device and holds its own copy for the same reason it imports
nothing else of ours.
"""

from dataclasses import dataclass

MAX_MESSAGE = 1024
"""How long a message may grow before it is taken for a broken sender. The
station's longest line is its status banner; nothing it says approaches this,
so a buffer that passes it is a stream that has lost its `>` and is dropped
rather than grown without bound."""

START = ord("<")
END = ord(">")

TRACKS = "ABCDEFGH"
"""The letters a track can be called. A `<p…>` line naming anything else —
`MAIN`, `PROG`, `JOIN` — is naming a **mode** rather than a district, and is
passed over: reading it as a track would put a district on the railroad that
the hardware does not have and leave the power reading `off` for good."""


@dataclass(frozen=True)
class Power:
    """What one `<p…>` line says: which track, and whether it reads on.

    `track` is empty on the line that names none, which the station sends
    only when every track is on or none is. The digit is `1` only for a track
    that is fully on — one that is powered but watching a rising current, and
    one that has tripped, both print `0` — so `on` here is "on", and anything
    else is a district a train may not move over.
    """

    track: str
    on: bool


@dataclass(frozen=True)
class Lock:
    """Whether the station says its emergency-stop lock is on: `<!PAUSED>`
    and `<!RESUMED>`, which it broadcasts on the lock changing and on being
    asked. This is the observation `stopped` is published from — never the
    fact that this app sent the lock command."""

    locked: bool


def messages(buffered: bytes, arrived: bytes) -> tuple[bytes, list[bytes]]:
    """Fold `arrived` into `buffered`: what is still partial, and the
    messages that completed, delimiters included and in the order they
    closed.

    Bytes outside a message are dropped — before a `<` there is nothing for
    them to belong to, and after a `>` the same — and a `<` inside a message
    starts it over, what came before never having been one.
    """
    partial = buffered
    whole: list[bytes] = []
    for byte in arrived:
        if byte == START:
            partial = b"<"
        elif not partial:
            continue
        elif byte == END:
            whole.append(partial + b">")
            partial = b""
        else:
            partial += bytes((byte,))
            if len(partial) > MAX_MESSAGE:
                partial = b""
    return partial, whole


def reply(message: bytes) -> Power | Lock | None:
    """The fact one whole message states, or None where it states neither of
    the two this app reads."""
    body = message[1:-1]
    if body == b"!PAUSED":
        return Lock(locked=True)
    if body == b"!RESUMED":
        return Lock(locked=False)
    if not body.startswith((b"p0", b"p1")):
        return None
    named = body[2:].strip().decode(errors="replace")
    if named == "":
        return Power(track="", on=body[1:2] == b"1")
    if len(named) == 1 and named in TRACKS:
        return Power(track=named, on=body[1:2] == b"1")
    return None
