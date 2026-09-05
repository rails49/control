"""The mapping: one desired value in, the exact bytes the station is sent out.

Every row of the device vocabulary this app recognises has a function here,
and each is **pure** — no socket, no state, no clock — so the whole protocol
is asserted as "this value, these bytes" on a machine with nothing plugged
in. The `<…>` syntax is this app's private business and appears nowhere else
in the repository (ADR-0043); [docs/dccex/README.md](../../../docs/dccex/README.md)
is where it is written down.

Three of the seven functions answer `None`. A value this app cannot put on a
wire — a position that is neither `closed` nor `thrown`, an aspect no head
here is wired for, a function value the station's binary `<F>` cannot express
— sends **nothing** rather than something near it: a translator that guessed
would move a turnout the layout did not ask for, and a faked action is worse
than silence, which is the same rule that keeps a commanded position from
being echoed back as a measured one (ADR-0022, ADR-0050).

The one word that is not a table row is here too, `STATUS`, the whole of what
a poll is made of, because it is bytes on the same wire and belongs beside
the rest of the protocol. So is `startup`, which is the one function that
maps nothing: it hands over what a person wrote, because a file of raw
station commands exists precisely so that this app needs no vocabulary for
what is in it.
"""

from tc49.lib.inventory import OFF, ON, STOPPED

STEPS = 126
"""What a speed's magnitude is scaled to. The station takes `0..126` and
maps `1..126` onto DCC steps `2..127`, keeping step 1 for the emergency stop
it sends itself; `0` is the ordinary stop and is what a `speed` of `0.0`
becomes."""

FORWARD = 1
REVERSE = 0
"""The station's direction bit: `1` is forward. A speed is signed for
direction along the track and its magnitude is the fraction of the
locomotive's maximum (CONTEXT.md, **Traction**), so the sign is read off here
and never reaches the wire as a number."""

CLOSED = "closed"
THROWN = "thrown"
"""The two positions a point takes. `thrown` writes a `1` into the accessory
packet, which is the polarity the station's own throttles and JMRI use."""

ASPECTS = {"stop": 0, "caution": 1, "clear": 2}
"""What each aspect this system shows is worth to the head wired to it.
`stop` is `0` because the extended accessory packet reserves it for stop; the
other two are this railroad's wiring and nothing above the layout interface
knows them, an **aspect** being a name rather than an enum (CONTEXT.md). A
name absent from here is a head this translator cannot show it on, so nothing
is sent."""

LINEAR_MAX = 2044
"""The accessory numbers a basic packet reaches, `1` upward: four
sub-addresses under each of 511 decoder addresses. What the drawing types on
a turnout is this number, the one a throttle and DecoderPro show, and
splitting it into the packet's address and sub-address is this app's."""

EXTENDED_MAX = 2047
"""The addresses an extended accessory packet reaches, its address field
being eleven bits. A signal is addressed in that space and not in the linear
one: it takes an aspect rather than a pair of positions, so nothing is split
off it."""

STATUS = b"<s>"
"""What a poll is made of, and the whole of it. An overload trip is **not
broadcast**: the station cuts the district and says so only on its USB
diagnostics, so `device/track` telling the truth would otherwise wait for a
person to notice. `<s>` makes it restate every track's power.

Nothing else is asked, because a station is polled only for what it can
answer. A question this one does not know is not passed over: the `!` opcode
takes no suffix here, so a lock query reads as the emergency stop itself and
every locomotive on the railroad stands once a second (#463)."""


def traction(addr: str, speed: float) -> bytes:
    """A locomotive's speed: `<t addr step dir>`.

    The magnitude is the fraction of that locomotive's maximum, so a fraction
    past `1.0` is full speed and never more — there is nothing above the
    maximum to ask for, and clamping is the one reading that cannot invent
    motion. `0.0` is step `0`, the ordinary stop, and takes the forward bit
    because a train standing still has no direction to state.

    Never `None`: `speed` is a number by the time it reaches here, and every
    number names a speed this station can be told.
    """
    magnitude = min(abs(speed), 1.0)
    direction = REVERSE if speed < 0 else FORWARD
    return f"<t {addr} {round(magnitude * STEPS)} {direction}>".encode()


def function(addr: str, number: str, value: bool) -> bytes:
    """A locomotive's function: `<F addr n 0|1>`.

    The station's function is a **switch** and so is the row that reaches it:
    a function is one bit here as it was everywhere else it was checked
    (ADR-0063). So every value the row can carry is one this station can be
    told, and this is **never `None`** for the reason `traction` is not —
    there is nothing left to refuse. What people mean by a range is decoder
    configuration, which is a different capability and no packet of this
    shape.
    """
    return f"<F {addr} {number} {int(value)}>".encode()


def point(addr: str, position: str) -> bytes | None:
    """A turnout's position, as a **stateless** accessory packet:
    `<a addr sub act>`.

    Stateless is the point of it. The station also keeps turnouts of its own
    and answers a throw with a position it has faked, and this app wants
    neither: `align` carries the points its transit needs every time, so a
    translator throws what it is told and holds no table (ADR-0031,
    ADR-0043), and a faked reply is what `device/point` is never published
    from.

    The address the drawing types is the accessory number a throttle shows,
    `1` upward; the packet wants a decoder address and a sub-address, so the
    number is split into them here — four sub-addresses to a decoder, the
    same arithmetic the station does for the one-argument form of the same
    command.
    """
    linear = _number(addr, LINEAR_MAX, least=1)
    if linear is None or position not in (CLOSED, THROWN):
        return None
    decoder, sub = divmod(linear - 1, 4)
    return f"<a {decoder + 1} {sub} {int(position == THROWN)}>".encode()


def signal(addr: str, aspect: str) -> bytes | None:
    """A signal head's aspect, as an extended accessory packet:
    `<A addr aspect>`.

    Extended and not basic, because a head shows three aspects where a basic
    packet has two positions. What each aspect is worth to the head is
    `ASPECTS` and is wiring, not contract: the dispatcher publishes a name
    and what a signal makes of it is a translator's (#203).
    """
    address = _number(addr, EXTENDED_MAX, least=0)
    if address is None or aspect not in ASPECTS:
        return None
    return f"<A {address} {ASPECTS[aspect]}>".encode()


def track(power: str) -> bytes:
    """The railroad's power, in the one word the whole railroad shares.

    `on` and `off` reach every track the station has, a power district being
    a hardware fact that does not reach the bus: there is one railroad-wide
    desired power and a translator maps it onto however many districts its
    hardware drives (SYSTEM.md, *Device vocabulary*).

    `stopped` is the **one-shot** emergency stop: every decoder told to stand
    with the track still live, and nothing afterwards. Any throttle on the
    shared port may drive away from it, this app's own included, and that is
    the intended reading rather than a defect in it — who may move a train is
    the operator's to decide, and the operator is the one holding the layout
    (#463).

    A station's emergency-stop *lock* would make `stopped` a state rather than
    an act, which is the better answer where a station has one and is not
    asked for here: it is one product's firmware-branch command, and a
    `stopped` that meant "under a lock" would put a station's private
    vocabulary inside a bus word every railroad shares (ADR-0043, #464).
    """
    if power == ON:
        return b"<1>"
    if power == STOPPED:
        return b"<!>"
    assert power == OFF, power
    return b"<0>"


def _number(addr: str, most: int, *, least: int) -> int | None:
    """An address as the station's own number, or None where it is no such
    address. Read and never trusted like any other field (SYSTEM.md, rule 4):
    the drawing types a plain string and nothing checks its shape there, so
    this is where a string that is no accessory number stops."""
    if not addr.isdigit():
        return None
    number = int(addr)
    return number if least <= number <= most else None


COMMENT = "#"
"""What a line of a startup file is a note on rather than a command. A person
writes the trip currents their four power districts really take, and the line
above each saying which district it is has to be a line the station never
sees."""


def startup(text: str) -> list[bytes]:
    """A startup file's text as the messages it sends, in the order written.

    **Not parsed beyond blank and comment.** Every other line is a string the
    station is handed exactly as typed, because the whole point of the file
    is that a person writes whatever their station understands — a per-district
    trip current, an auto-reverser, a polarity — without this app growing a
    vocabulary for it. Nothing here knows what a district is, and nothing
    above the layout interface learns that this railroad has four of them
    (#217).

    Surrounding whitespace goes: it is how a file is laid out and not part of
    any message, and a line that is nothing else is skipped.
    """
    lines = (line.strip() for line in text.splitlines())
    return [line.encode() for line in lines if line and not line.startswith(COMMENT)]
