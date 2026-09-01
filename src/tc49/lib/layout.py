"""Layout: blocks, connections, transits, conflicts, terminal blocks.

The validated in-memory form of a layout document (LAYOUT.md). Validation
happens at construction — a mistyped end is a load-time error naming the
fault, never a ``KeyError`` mid-run. The conflict matrix is expanded from
``concurrent`` by inversion (ADR-0006): every pair of transits at a
connection conflicts unless declared, and transits are self-exclusive.
Terminal blocks are derived, never declared. A connection also carries the
``points`` each of its transits needs thrown (ADR-0031), an appendix to the
transits and the whole of the hardware the layout knows about. Routing stays
outside — Layout is a data structure, not a policy.

The ``check_*`` helpers are shared with the scenario validation in
``store.py``. The ``<block>.<A|B>`` end form is parsed here and nowhere else:
``check_end`` validates one, ``block_of``, ``end_letter`` and ``opposite_end``
take one apart, ``end_on`` reads one off a transit and ``end_crossed`` does
the same for a transit that came off the bus with ``end_across`` answering
the other side of it, ``connected_end`` says which end of a block a connection
holds, and ``departure_end`` composes that over ``opposite_end`` into the end
a train leaves a block by. The ``<block>.<A-to-B|B-to-A>`` **facing** form is
parsed beside it and nowhere else: ``FACINGS`` is the vocabulary,
``facing_ends`` takes one apart into the two ends it runs between,
``facing_towards`` writes one from the end a train would depart through, and
``connected_facing`` is ``connected_end`` asked of one.
"""

from collections.abc import Container
from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True)
class Point:
    """An address and the position a way wants the point wearing it in.

    The whole of the hardware the layout knows about (ADR-0031): never a
    shape, a place on the canvas, or a switching time. Two points may share
    an address and then move together, so a way can name one address twice.
    """

    addr: str
    position: str


@dataclass(frozen=True)
class Connection:
    name: str
    transits: dict[str, tuple[str, str]]  # transit name -> unordered end pair
    concurrent: frozenset[frozenset[str]]  # declared exceptions, by transit name
    points: dict[str, tuple[Point, ...]]  # transit name -> the points its way needs


@dataclass(frozen=True)
class Layout:
    name: str
    blocks: dict[str, int]  # block name -> length
    connections: dict[str, Connection]
    terminal_blocks: frozenset[str]
    end_connection: dict[str, str]  # block end -> the one connection holding it

    @classmethod
    def from_document(cls, doc: Any) -> "Layout":
        check_keys(
            doc, "layout document", {"layout", "blocks", "connections"}, {"units"}
        )
        name = doc["layout"]
        check_name(name, "layout")

        blocks: dict[str, int] = {}
        for block, spec in as_mapping(
            doc["blocks"], f"layout '{name}': blocks"
        ).items():
            check_name(block, f"layout '{name}': block")
            check_keys(spec, f"block '{block}'", {"length"})
            blocks[block] = check_length(
                spec["length"], f"layout '{name}': block '{block}'"
            )

        connections: dict[str, Connection] = {}
        end_owner: dict[str, str] = {}  # block end -> owning connection
        for conn, spec in as_mapping(
            doc["connections"], f"layout '{name}': connections"
        ).items():
            check_name(conn, f"layout '{name}': connection")
            where = f"layout '{name}': connection '{conn}'"
            check_keys(spec, where, {"transits"}, {"concurrent", "points"})

            transits: dict[str, tuple[str, str]] = {}
            for transit, raw_ends in as_mapping(
                spec["transits"], f"{where}: transits"
            ).items():
                check_name(transit, f"{where}: transit")
                if (
                    not isinstance(raw_ends, list)
                    or len(cast(list[Any], raw_ends)) != 2
                ):
                    raise ValueError(
                        f"{where}: transit '{transit}' must join two distinct"
                        f" ends, got {raw_ends!r}"
                    )
                ends = [
                    check_end(end, blocks, f"{where}: transit '{transit}'")
                    for end in cast(list[Any], raw_ends)
                ]
                if ends[0] == ends[1]:
                    raise ValueError(
                        f"{where}: transit '{transit}' must join two distinct"
                        f" ends, got {raw_ends!r}"
                    )
                for end in ends:
                    owner = end_owner.setdefault(end, conn)
                    if owner != conn:
                        raise ValueError(
                            f"layout '{name}': end '{end}' belongs to both"
                            f" connection '{owner}' and '{conn}' — a block end"
                            f" belongs to at most one connection"
                        )
                transits[transit] = (ends[0], ends[1])

            connections[conn] = Connection(
                conn,
                transits,
                check_concurrent(spec.get("concurrent"), transits, where),
                check_points(spec.get("points"), transits, where),
            )

        terminals = frozenset(
            block
            for block in blocks
            if (f"{block}.A" in end_owner) != (f"{block}.B" in end_owner)
        )
        return cls(name, blocks, connections, terminals, end_owner)

    def transits_at(self, end: str) -> list[tuple[str, str]]:
        """The transits crossing `end`, as (qualified transit id, end across)."""
        conn = self.end_connection.get(end)
        if conn is None:
            return []
        result: list[tuple[str, str]] = []
        for transit, (a, b) in self.connections[conn].transits.items():
            if end in (a, b):
                result.append((f"{conn}.{transit}", b if end == a else a))
        return result

    def conflicts(self, a: str, b: str) -> bool:
        """Whether transits `a` and `b` (as 'connection.transit') exclude
        each other."""
        conn_a, transit_a = self._resolve(a)
        conn_b, transit_b = self._resolve(b)
        if conn_a != conn_b:
            return False
        if transit_a == transit_b:
            return True
        pair = frozenset((transit_a, transit_b))
        return pair not in self.connections[conn_a].concurrent

    def _resolve(self, transit_id: str) -> tuple[str, str]:
        conn, _, transit = transit_id.partition(".")
        if (
            conn not in self.connections
            or transit not in self.connections[conn].transits
        ):
            raise ValueError(f"layout '{self.name}': unknown transit '{transit_id}'")
        return conn, transit


def as_mapping(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{what} must be a mapping, got {type(value).__name__}")
    return cast(dict[str, Any], value)


def check_keys(
    doc: Any, what: str, required: set[str], optional: set[str] | None = None
) -> None:
    as_mapping(doc, what)
    if unknown := set(doc) - required - (optional or set()):
        raise ValueError(f"{what}: unknown key(s) {sorted(unknown)}")
    if missing := required - set(doc):
        raise ValueError(f"{what}: missing key(s) {sorted(missing)}")


def check_name(name: Any, what: str) -> None:
    if not isinstance(name, str) or not name or "." in name or "/" in name:
        raise ValueError(f"{what} name {name!r} must be a string without '.' or '/'")


def check_length(length: Any, where: str) -> int:
    if not isinstance(length, int) or length <= 0:
        raise ValueError(f"{where}: length must be a positive integer, got {length!r}")
    return length


def check_concurrent(
    spec: Any, transits: Container[str], where: str
) -> frozenset[frozenset[str]]:
    """Validate a `concurrent` declaration against the transits it may name.
    A layout's connections and a drawing's symbols declare concurrency in the
    same shape, one level apart, so they share the check."""
    concurrent: set[frozenset[str]] = set()
    for raw_pair in cast(list[Any], spec or []):
        pair = (
            [str(t) for t in cast(list[Any], raw_pair)]
            if isinstance(raw_pair, list)
            else []
        )
        if len(pair) != 2 or pair[0] == pair[1]:
            raise ValueError(
                f"{where}: concurrent entry must pair two distinct transits,"
                f" got {raw_pair!r}"
            )
        for transit in pair:
            if transit not in transits:
                raise ValueError(
                    f"{where}: concurrent names unknown transit '{transit}'"
                )
        concurrent.add(frozenset(pair))
    return frozenset(concurrent)


def check_points(
    spec: Any, transits: Container[str], where: str
) -> dict[str, tuple[Point, ...]]:
    """Validate a `points` declaration against the transits it may name.

    It is an appendix to the transits, not a second level of description, so
    every key is a transit of the same connection and a transit with nothing
    to throw is absent rather than empty (ADR-0031).
    """
    points: dict[str, tuple[Point, ...]] = {}
    for transit, raw in as_mapping(spec or {}, f"{where}: points").items():
        if transit not in transits:
            raise ValueError(f"{where}: points names unknown transit '{transit}'")
        entries: list[Point] = []
        for entry in cast(list[Any], raw if isinstance(raw, list) else []):
            check_keys(
                entry, f"{where}: transit '{transit}': point", {"addr", "position"}
            )
            position = entry["position"]
            if position not in ("closed", "thrown"):
                raise ValueError(
                    f"{where}: transit '{transit}': position must be 'closed' or"
                    f" 'thrown', got {position!r}"
                )
            entries.append(Point(str(entry["addr"]), position))
        if not entries:
            raise ValueError(
                f"{where}: transit '{transit}' lists no point — a transit with"
                f" nothing to throw is left out of points"
            )
        points[transit] = tuple(entries)
    return points


def check_end(end: Any, blocks: dict[str, int], where: str) -> str:
    """Validate an '<block>.<A|B>' end reference and return it as a string."""
    block, dot, letter = str(end).partition(".")
    if not dot or letter not in ("A", "B"):
        raise ValueError(f"{where}: end '{end}' must be '<block>.A' or '<block>.B'")
    if block not in blocks:
        raise ValueError(f"{where}: end '{end}' names unknown block '{block}'")
    return str(end)


def block_of(end: str) -> str:
    """The block a validated '<block>.<A|B>' end reference belongs to, and a
    bare block name unchanged: partitioning on a dot that is not there gives
    the whole string back, so a caller reading either says it the one way."""
    return end.partition(".")[0]


def end_letter(end: str) -> str:
    """The 'A' or 'B' of a validated '<block>.<A|B>' end reference, and — a
    facing being written the same way — the 'A-to-B' or 'B-to-A' of one."""
    return end.partition(".")[2]


def opposite_end(end: str) -> str:
    """The other end of the same block: a block has exactly A and B."""
    return f"{block_of(end)}.{'B' if end_letter(end) == 'A' else 'A'}"


def connected_end(layout: Layout, candidate: str) -> str:
    """The end of `candidate`'s block that a connection holds: `candidate`
    itself where one holds it, the block's other end otherwise.

    A pure layout question, and the reason it is asked is that a **terminal
    block** is defined as a block with only one connected end. A terminal
    block is the only block where the candidate can be a wall and a connected
    end still exists, and it has exactly one of those, so the answer is never
    a second wall. It is the physical railroad settling what the pass-through
    rule leaves open: a train that entered a stub faces away from its entry
    end, there is no such end, and one end is all it can leave by (#145).
    Both the scheduler, which holds facing, and the dispatcher, which supplies
    a departure end for a request queued behind a route it has yet to choose
    (#135), ask the same question, so it is answered once here.
    """
    return candidate if candidate in layout.end_connection else opposite_end(candidate)


def departure_end(layout: Layout, lie: str) -> str:
    """The end a train lying `lie` in its block leaves it by: the other end
    of that block, or a terminal block's one connected end.

    `lie` is the way the train lies said either way — the end it came in
    through, `'<block>.A'`, or the **facing** it holds, `'<block>.A-to-B'`.
    The two are one trajectory: a train faces away from the end it entered
    through, so a train that came in at A and a train facing A-to-B both
    leave by B. Both callers today hold the entered end; a caller holding a
    facing asks the same question and gets the same answer, which is the
    whole of what saying a facing as a run buys (#241).

    The composed rule — `connected_end` applied to the far side of the end
    the train came in through — and the whole of what a strict pass-through
    means for one block (ADR-0001, CONTEXT.md **facing**). Everything that
    settles where a train goes out asks it: the scheduler of a move it saw
    granted, the dispatcher of the route it has just committed to. It takes
    the end and not a route, since `lib` has no reason to know what a `Route`
    is and one of those callers does not have one to pass — reading the
    entered end off a route stays with the dispatcher (#155).
    """
    entered = lie if end_letter(lie) in ("A", "B") else facing_ends(lie)[0]
    return connected_end(layout, opposite_end(entered))


FACINGS = ("A-to-B", "B-to-A")
"""The two ways a train lies in its block, each written as the run it would
make across it: a train facing 'A-to-B' would depart nose-first through B.

The whole vocabulary of a **facing** value, which is written `<block>.A-to-B`
on `tc49/schedule/state/facing` and bare in a scenario's placement, the block
being the `at` beside it. Stated as the run and not as the end reached because
the end alone cannot be read without the convention in front of you (#241)."""


def facing_ends(facing: str) -> tuple[str, str]:
    """The two ends a facing runs between, tail first: a train facing
    '<block>.A-to-B' stands with its tail at '<block>.A' and its nose — the
    end it would depart through where a connection holds one — at
    '<block>.B'."""
    tail, _, nose = end_letter(facing).partition("-to-")
    return f"{block_of(facing)}.{tail}", f"{block_of(facing)}.{nose}"


def facing_towards(end: str) -> str:
    """The facing of a train that would depart through `end`.

    The inverse of `facing_ends`'s nose, and how every site that settles a
    facing writes one down: what the layout answers is an end, and what the
    scheduler holds is a facing (ADR-0019)."""
    return f"{block_of(end)}.{'A-to-B' if end_letter(end) == 'B' else 'B-to-A'}"


def connected_facing(layout: Layout, candidate: str) -> str:
    """`candidate` where a connection holds the end it points at, and the same
    facing turned around otherwise: `connected_end` asked of a facing.

    A terminal block is the one block where a placement, or a facing carried
    into a new block, can point a train at the wall, and its one connected end
    is the answer whatever the candidate says (#145).
    """
    return facing_towards(connected_end(layout, facing_ends(candidate)[1]))


def end_on(layout: Layout, block: str, transit: str) -> str:
    """The end of `block` that `transit` crosses.

    Which end that is does not depend on which way a train is going over it:
    leaving, it is the departure end the train goes out through, and so the
    signal the aspect belongs to; entering, it is the arrival end the train
    comes in through. Neither is on the bus — `move_granted` names the transit
    and the block, and `route_chosen` names the route — so both the dispatcher
    and the scheduler read it from the layout here.

    It takes the two names as the layout's own, which is what the dispatcher
    holds: the route it just chose crosses the blocks it is made of. A caller
    holding names that came off the bus asks `end_crossed` below.
    """
    connection, _, name = transit.partition(".")
    first, second = layout.connections[connection].transits[name]
    return first if block_of(first) == block else second


def end_crossed(layout: Layout, block: str, transit: str) -> str | None:
    """`end_on` asked of names that came off the bus: the end of `block` that
    `transit` crosses, or None where the layout holds no such transit or that
    transit crosses neither end of that block.

    A consumer may not raise on a payload (SYSTEM.md, rule 4), and `end_on`
    reaches straight into the layout, so a transit no connection here holds is
    a `KeyError` out of a handler. The pair is read together because a grant
    names both and neither is meaningful alone: a transit crossing no end of
    the block named leaves no end to face away from, and answering the far
    block's end instead would carry a frame the layout contradicts into
    facing.
    """
    connection, _, name = transit.partition(".")
    held = layout.connections.get(connection)
    ends = held.transits.get(name) if held is not None else None
    if ends is None:
        return None
    first, second = ends
    if block_of(first) == block:
        return first
    return second if block_of(second) == block else None


def end_across(layout: Layout, block: str, transit: str) -> str | None:
    """The end `transit` crosses on its other side from `block`, or None where
    the layout holds no such transit or that transit crosses neither end of
    that block.

    `end_on` read from the other side and asked of names that came off the
    bus, which is what a binding handed a `move` asks: the command names the
    block the train is to end up in, and the block across the transit from
    there is the one it must be standing in now (ADR-0047).

    Named for the axis it reads along. The far end of a *block* is its second
    sensor, the one a train trips after the near one as it enters, so the name
    this lookup carried until #279 said a different axis in the very module a
    hardware binding reads.

    It fails the two ways `end_crossed` fails, and answers None for both. A
    transit under no connection here, or one no connection declares, is a
    `KeyError` for a caller reaching into the layout and a payload is never a
    reason to raise (rule 4). A transit the layout does hold that crosses
    neither end of `block` reaches no block a train could be standing in to
    take it: answering its first end anyway would hand back a near end for a
    run there is no track for, and a command describing something the layout
    does not do has nothing to execute (#276).
    """
    connection, _, name = transit.partition(".")
    held = layout.connections.get(connection)
    ends = held.transits.get(name) if held is not None else None
    if ends is None:
        return None
    first, second = ends
    if block_of(first) == block:
        return second
    return first if block_of(second) == block else None
