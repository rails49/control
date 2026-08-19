"""Drawing: the authored schematic, and the derivation of a layout from it.

The drawing is the source of truth (ADR-0015); the layout is derived on
``get`` and never authored. A drawing is symbols joined by wires through
their pins, and wire shape carries no meaning — derivation reads only which
pin connects to which, so moving a symbol can never change the derived
layout. The format is [DRAWING.md](../../../docs/store/DRAWING.md).

Validation splits in two. The *schema* is checked at construction, so a
document that loads is well-formed. The *pin rules* — every pin holds exactly
two connections, every portal label is worn by exactly two portals — are
checked at derivation instead: work in progress can be parked with a dangling
pin and saved, but a ``get`` never returns a layout from an incomplete
drawing.

Derivation is DRAWING.md's three passes:

1. connected components of the non-block symbols give the connections;
2. walking symbol transits between a component's block ends gives the
   connection transits;
3. composing symbol concurrency pairwise over those transits gives
   ``concurrent``.

The result is a layout *document* in canonical key order, which the store
hands to the existing validator as a safety net against derivation bugs.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, cast

from tc49.lib.layout import (
    as_mapping,
    check_concurrent,
    check_keys,
    check_length,
    check_name,
)

# The symbol library: the kinds whose geometry is fixed, and the transits each
# one has. A crossing and the slips share four pins, two per route, named for
# the route and the side: `a1` and `b1` on one side, `a2` and `b2` on the
# other. A slip is then a route from one side to the other over the other
# track, which is also why the double slip is two turnouts joined toe to toe.
# None of them declares anything concurrent — every route through a crossing
# or a slip takes the shared frog, and a turnout's two routes share its toe.
#
# The two 90 degree crossings offer the through routes and no slip, and are two
# kinds rather than two appearances of one because their footprints and pin
# positions differ (ui/EDITOR.md).
#
# `LIBRARY`, `PINS` and `ROTATIONS` are public because the editor's TypeScript
# is generated from them (symbols.py); the rest of the module's constants are
# its own.
_CROSS = ("a1", "a2", "b1", "b2")
_THROUGH = {"a": ("a1", "a2"), "b": ("b1", "b2")}
LIBRARY: dict[str, dict[str, tuple[str, str]]] = {
    "turnout": {"straight": ("toe", "straight"), "diverging": ("toe", "diverging")},
    "crossing": dict(_THROUGH),
    "crossing_90": dict(_THROUGH),
    "crossing_90d": dict(_THROUGH),
    "single_slip": {**_THROUGH, "slip": ("a1", "b2")},
    "double_slip": {**_THROUGH, "slip_1": ("a1", "b2"), "slip_2": ("b1", "a2")},
}

# What each leg of a motorised kind wants the motor set to (ADR-0022). Every
# motorised kind has one motor and two positions: a turnout lies straight or
# diverging, a slip straight or curved, both roads together. A turnout's legs
# are already named for its positions and a slip's are not, so the table says
# it once, here, rather than in every reader of a way.
#
# It is also the roll of kinds that have a motor at all, which is what takes an
# `addr`; a fixed crossing is not in it and takes none.
POSITIONS: dict[str, dict[str, str]] = {
    "turnout": {"straight": "straight", "diverging": "curved"},
    "single_slip": {"a": "straight", "b": "straight", "slip": "curved"},
    "double_slip": {
        "a": "straight",
        "b": "straight",
        "slip_1": "curved",
        "slip_2": "curved",
    },
}

# `pin` (a free-standing bend) and `portal` are joiners: they pass a wire
# through and derive to nothing. The bend is named because the editor treats it
# apart from every other kind — it is placed by clicking empty canvas rather
# than from the palette — and one spelling of it beats two.
BEND = "pin"
PINS: dict[str, tuple[str, ...]] = {
    "block": ("A", "B"),
    "terminal": ("P",),
    "portal": ("P",),
    "pin": ("P",),
    "turnout": ("toe", "straight", "diverging"),
    "crossing": _CROSS,
    "crossing_90": _CROSS,
    "crossing_90d": _CROSS,
    "single_slip": _CROSS,
    "double_slip": _CROSS,
}
_JOINERS = frozenset({BEND, "portal"})

# Where a symbol sits on the canvas (ADR-0018). Derivation reads none of it, so
# the schema check is all there is: a placement that loads is well-formed, and
# nothing downstream can be changed by moving anything. Every kind is drawn one
# way, so where it sits is the whole of its geometry.
_PLACEMENT = frozenset({"at", "rot", "flip"})
ROTATIONS = (0, 90, 180, 270)

Use = tuple[str, str]  # a symbol and the local transit a walk took through it
Walk = tuple[tuple[str, str], tuple[Use, ...]]  # the block ends, and the way


class Refusal(ValueError):
    """A refusal about a way through the drawing, carrying the walks behind it.

    Two of derivation's refusals say something about a route rather than about
    any one symbol, and the editor lights that route on the canvas rather than
    printing the sentence beside it (ADR-0024). The walk is known where the
    refusal is raised, so it travels with it; parsing it back out of the
    message would be deriving topology a second time, in the front end.
    """

    def __init__(self, message: str, *ways: Walk) -> None:
        super().__init__(message)
        self.ways = ways


@dataclass(frozen=True)
class Symbol:
    """A symbol declares pins, transits between them, and which transit pairs
    are concurrent — the shape of a connection, one level down."""

    name: str
    kind: str
    pins: tuple[str, ...]
    transits: dict[str, tuple[str, str]] = field(default_factory=dict[str, Any])
    concurrent: frozenset[frozenset[str]] = frozenset()
    names: dict[str, str] = field(default_factory=dict[str, Any])  # transit -> name
    connection: str = ""  # the junction this symbol belongs to, where authored
    length: int = 0
    label: str = ""  # a portal's, which pairs it with its mate
    addr: str = ""  # a motorised symbol's, naming what the hardware answers to


@dataclass(frozen=True)
class Drawing:
    name: str
    symbols: dict[str, Symbol]
    wires: tuple[tuple[str, str], ...]  # pins, written '<symbol>.<pin>'
    units: str | None = None
    # A wire joining two blocks is itself the connection holding their one
    # transit, so it carries the name. Keyed by the wire's pins, sorted.
    wire_connections: dict[tuple[str, str], str] = field(
        default_factory=dict[tuple[str, str], str]
    )

    @classmethod
    def from_document(cls, doc: Any) -> "Drawing":
        check_keys(doc, "drawing document", {"drawing", "symbols"}, {"units", "wires"})
        name = doc["drawing"]
        check_name(name, "drawing")

        symbols: dict[str, Symbol] = {}
        for symbol, spec in as_mapping(
            doc["symbols"], f"drawing '{name}': symbols"
        ).items():
            check_name(symbol, f"drawing '{name}': symbol")
            symbols[symbol] = _symbol(
                f"drawing '{name}': symbol '{symbol}'", symbol, spec
            )

        raw_wires: Any = doc.get("wires") or []
        if not isinstance(raw_wires, list):
            raise TypeError(f"drawing '{name}': wires must be a list")
        wires: list[tuple[str, str]] = []
        wire_connections: dict[tuple[str, str], str] = {}
        for raw in cast(list[Any], raw_wires):
            where = f"drawing '{name}': wire"
            pins, connection = _wire(raw, where)
            a, b = _pin_pair(pins, where)
            wire = (_check_pin(a, symbols, where), _check_pin(b, symbols, where))
            wires.append(wire)
            if connection:
                wire_connections[cast(tuple[str, str], tuple(sorted(wire)))] = (
                    connection
                )

        return cls(name, symbols, tuple(wires), doc.get("units"), wire_connections)

    def derive(self) -> dict[str, Any]:
        """The layout document this drawing describes, in canonical order."""
        grouped = self._transits()
        return {
            "layout": self.name,
            **({} if self.units is None else {"units": self.units}),
            "blocks": {
                symbol.name: {"length": symbol.length}
                for symbol in self._of_kind("block")
            },
            "connections": {
                connection: self._connection(grouped[connection])
                for connection in sorted(grouped)
            },
        }

    def explain(self) -> dict[str, Any]:
        """Why the layout is what it is: the way each transit takes, and for
        each pair that cannot run together, the symbols they share.

        Derivation computes both and keeps neither, the layout having nowhere
        to put them. A list of exclusive pairs states the outcome; naming the
        frog behind one states the reason, which is the thing the editor is
        built to show (EDITOR.md).
        """
        return {
            "layout": self.name,
            "connections": {
                connection: {
                    "transits": {
                        name: {
                            "ends": list(ends),
                            "way": [list(use) for use in used],
                        }
                        for name, (ends, used) in sorted(named.items())
                    },
                    "exclusive": [
                        {"transits": [one, two], "shared": shared}
                        for i, one in enumerate(sorted(named))
                        for two in sorted(named)[i + 1 :]
                        if (shared := self._blocking(named[one][1], named[two][1]))
                    ],
                }
                for connection, named in sorted(self._transits().items())
            },
        }

    def review(self) -> dict[str, Any]:
        """Everything the editor draws that the document does not hold.

        Red pins, unpaired portal labels and junction regions are wanted
        exactly when the drawing is incomplete, which is when derivation
        refuses, so each is worked out without raising and the refusal is
        reported rather than thrown. A refusal names one fault and stops,
        which is why the findings are lists and it is not. That
        is what lets the front end own placement and rendering and no topology
        at all (EDITOR.md).
        """
        offending: tuple[Walk, ...] = ()
        try:
            layout, explain, refused = self.derive(), self.explain(), None
        except ValueError as refusal:
            layout, explain, refused = None, None, str(refusal)
            offending = refusal.ways if isinstance(refusal, Refusal) else ()
        return {
            "red_pins": self.red_pins(),
            "unpaired_portals": self.unpaired_portals(),
            "junctions": self.junctions(),
            "joints": self.joints(),
            "layout": layout,
            "explain": explain,
            "refused": refused,
            "offending": [
                {"ends": list(ends), "way": [list(use) for use in used]}
                for ends, used in offending
            ],
        }

    def junctions(self) -> list[dict[str, Any]]:
        """The symbol groups the editor tints as one region, each with the name
        its connection takes.

        A component that declares no transit is not a junction: a terminal
        capping a block end is its own component and derives nothing, and
        tinting it would say otherwise.

        `name` is `None` where the drawing has not settled one, reported rather
        than raised because that is the normal state of a junction a moment
        after it is drawn. `names` is what its symbols write as `connection`,
        which is what tells the two unnamed cases apart: nothing written is a
        junction to be minted, and several written is a disagreement someone
        typed, which derivation refuses and the editor leaves alone.
        """
        found: list[dict[str, Any]] = []
        for group in self._groups(self._loose_joins()):
            if not any(self.symbols[symbol].transits for symbol in group):
                continue
            try:
                name = self._connection_name(group)
            except ValueError:
                name = None
            declared = sorted({self.symbols[s].connection for s in group} - {""})
            found.append({"name": name, "names": declared, "symbols": group})
        return found

    def joints(self) -> list[dict[str, Any]]:
        """The ways from one block end to another that cross no symbol
        declaring a transit. Each is a connection in itself and carries its
        name on one of its own wires (DRAWING.md).

        The editor mints those names, so it has to be told which wires want
        one, and it cannot work that out itself without walking the drawing —
        which is the one thing the front end does not do. Reported rather than
        raised, since a joint drawn a moment ago has no name yet. `name` is the
        one the chain carries; `names` is every name on it, which tells an
        unnamed joint from one named twice the way `junctions` does.
        """
        found: list[dict[str, Any]] = []
        for ends, used in self._walks(self._loose_joins()):
            if any(self.symbols[symbol].transits for symbol, _ in used):
                continue
            chain = self._chain(ends, used)
            named = sorted(
                {
                    self.wire_connections[key]
                    for key in chain
                    if key in self.wire_connections
                }
            )
            found.append(
                {
                    "ends": list(ends),
                    "wires": [list(wire) for wire in chain],
                    "name": named[0] if len(named) == 1 else None,
                    "names": named,
                }
            )
        return sorted(found, key=lambda joint: joint["ends"])

    def red_pins(self) -> list[str]:
        """The pins that do not hold the wires they take: one for a symbol
        pin, two for a free-standing bend. Saving such a drawing is allowed
        and deriving it is refused, so this never raises."""
        joins = self._wire_joins()
        return sorted(
            node
            for symbol in self.symbols.values()
            for pin in symbol.pins
            if len(joins[node := f"{symbol.name}.{pin}"]) != _wires_wanted(symbol)
        )

    def unpaired_portals(self) -> list[dict[str, Any]]:
        """The labels no pair wears, each with the portals wearing it: worn
        once, or worn three times and more, since a label pairs exactly two.

        Reported rather than raised for the reason red pins are: derivation
        names one label and stops, so a drawing with two lone portals would
        report one and reveal the next on the fix, and the editor has to be
        told about all of them at once (EDITOR.md#validation)."""
        return [
            {"label": label, "portals": sorted(worn_by)}
            for label, worn_by in sorted(self._portals().items())
            if len(worn_by) != 2
        ]

    def _transits(self) -> dict[str, dict[str, Walk]]:
        """Every transit, by connection and by derived name, with the way it
        takes. The whole of passes 1 and 2, shared by `derive` and `explain`
        so that neither can disagree with the other about what exists."""
        joins = self._joins()
        connection_of = self._connections(joins)

        grouped: dict[str, list[Walk]] = defaultdict(list)
        spent: set[tuple[str, str]] = set()
        for ends, used in self._walks(joins):
            if ends[0] == ends[1]:
                raise Refusal(
                    f"drawing '{self.name}': the way out of '{ends[0]}' leads"
                    f" back into it — a transit joins two distinct block ends",
                    (ends, used),
                )
            connection = connection_of[used[0][0]] if used else None
            if connection is None:
                connection = self._joint_name(ends, used, spent)
            grouped[connection].append((ends, used))

        for wire in sorted(set(self.wire_connections) - spent):
            raise ValueError(
                f"drawing '{self.name}': the wire {list(wire)} names a"
                f" connection '{self.wire_connections[wire]}', but it does not"
                f" join two blocks — only a wire that is itself the connection"
                f" carries a name"
            )
        return {
            connection: self._named(connection, walks)
            for connection, walks in grouped.items()
        }

    def _named(self, connection: str, walks: list[Walk]) -> dict[str, Walk]:
        where = f"drawing '{self.name}': connection '{connection}'"
        named: dict[str, Walk] = {}
        for ends, used in walks:
            name = self._transit_name(where, ends, used)
            if name in named:
                raise Refusal(
                    f"{where}: two transits named '{name}' — name one of them"
                    f" in the drawing",
                    named[name],
                    (ends, used),
                )
            named[name] = (ends, used)
        return named

    def _joint_name(
        self, ends: tuple[str, str], used: tuple[Use, ...], spent: set[tuple[str, str]]
    ) -> str:
        """The name of the connection a bare wire between two blocks is.

        Its way crosses no symbol that declares transits, so nothing along it
        can name it and the wire carries the name instead. Routed around a
        corner the joint is several wires through bend pins, and the name may
        sit on any one of them, so the whole chain is searched. Two names on
        one chain are refused rather than resolved by order, the same as two
        symbol transits naming one way."""
        chain = self._chain(ends, used)
        named = sorted(
            {
                self.wire_connections[key]
                for key in chain
                if key in self.wire_connections
            }
        )
        if len(named) > 1:
            raise ValueError(
                f"drawing '{self.name}': the joint from '{ends[0]}' to"
                f" '{ends[1]}' is named {named} — one joint takes one name"
            )
        if not named:
            raise ValueError(
                f"drawing '{self.name}': the way from '{ends[0]}' to"
                f" '{ends[1]}' runs through no connection symbol — blocks are"
                f" joined through one, or by a wire that names the connection"
                f" it is"
            )
        spent.update(key for key in chain if key in self.wire_connections)
        return named[0]

    def _chain(
        self, ends: tuple[str, str], used: tuple[Use, ...]
    ) -> list[tuple[str, str]]:
        """The wires one way is drawn from, as sorted pin pairs. Routed around
        a corner a joint is several wires through bend pins, and it is the
        chain rather than any one wire that is the connection."""
        held = {ends[0], ends[1]} | {
            f"{symbol}.{pin}" for symbol, _ in used for pin in self.symbols[symbol].pins
        }
        return [
            cast(tuple[str, str], tuple(sorted(wire)))
            for wire in self.wires
            if held.issuperset(wire)
        ]

    # --- the pin rules, checked at derivation, never at save ---------------

    def _joins(self) -> dict[str, list[str]]:
        """Every pin and what it joins: its wires, plus the pairing a portal
        wears. A joint is a joint however it is drawn, so portal pairs make
        the graph one connected whole before anything walks it."""
        portals = self._portals()
        for label, worn_by in sorted(portals.items()):
            if len(worn_by) != 2:
                raise ValueError(
                    f"drawing '{self.name}': portal label '{label}' is worn by"
                    f" {len(worn_by)} portal(s) — a label pairs exactly two"
                )

        joins = self._wire_joins()
        for symbol in self.symbols.values():
            wires = _wires_wanted(symbol)
            for pin in symbol.pins:
                node = f"{symbol.name}.{pin}"
                if len(joins[node]) == wires:
                    continue
                if wires == 2:
                    raise ValueError(
                        f"drawing '{self.name}': free-standing pin '{node}'"
                        f" joins two wires, got {len(joins[node])}"
                    )
                raise ValueError(
                    f"drawing '{self.name}': pin '{node}' takes one wire, got"
                    f" {len(joins[node])} — every pin holds exactly two"
                    f" connections, and a deliberate track end takes a"
                    f" terminal symbol"
                )

        for worn_by in portals.values():
            _pair(joins, worn_by)
        return joins

    def _portals(self) -> dict[str, list[str]]:
        portals: dict[str, list[str]] = defaultdict(list)
        for symbol in self._of_kind("portal"):
            portals[symbol.label].append(symbol.name)
        return portals

    def _wire_joins(self) -> dict[str, list[str]]:
        """Every pin and what a wire joins it to, with nothing checked, which
        is what lets an incomplete drawing still be looked at."""
        joins: dict[str, list[str]] = defaultdict(list)
        for a, b in self.wires:
            joins[a].append(b)
            joins[b].append(a)
        return joins

    def _loose_joins(self) -> dict[str, list[str]]:
        """`_joins` without the checks: portals pair where a label happens to
        be worn twice, and a pin short of its wires is simply short."""
        joins = self._wire_joins()
        for worn_by in self._portals().values():
            if len(worn_by) == 2:
                _pair(joins, worn_by)
        return joins

    # --- pass 1: components of non-block symbols give the connections ------

    def _connections(self, joins: dict[str, list[str]]) -> dict[str, str | None]:
        """Each non-block symbol, mapped to the name of the connection its
        component derives — `None` where the component declares no transits
        and so has nothing to take a name from."""
        named: dict[str, str | None] = {}
        taken: dict[str, list[str]] = {}
        for group in self._groups(joins):
            name = self._connection_name(group)
            if name is not None:
                if name in taken:
                    raise ValueError(
                        f"drawing '{self.name}': two junctions are named"
                        f" '{name}' — {taken[name]} and {group}"
                    )
                taken[name] = group
            for symbol in group:
                named[symbol] = name
        return named

    def _groups(self, joins: dict[str, list[str]]) -> list[list[str]]:
        """The connected components of the non-block symbols: one junction
        each, whether or not the drawing is complete enough to name them."""
        component: dict[str, str] = {
            symbol.name: symbol.name
            for symbol in self.symbols.values()
            if symbol.kind != "block"
        }

        def root(symbol: str) -> str:
            # Halve the path as we climb. The two assignments have to stay
            # apart: written `symbol = component[symbol] = ...`, the rebound
            # `symbol` is what the second target indexes, which makes the
            # grandparent its own root and cuts the chain in two.
            while component[symbol] != symbol:
                component[symbol] = component[component[symbol]]
                symbol = component[symbol]
            return symbol

        for node, joined in sorted(joins.items()):
            here = node.partition(".")[0]
            if here not in component:
                continue
            for other in joined:
                there = other.partition(".")[0]
                if there in component:
                    component[root(here)] = root(there)

        members: dict[str, list[str]] = defaultdict(list)
        for symbol in sorted(component):
            members[root(symbol)].append(symbol)
        return list(members.values())

    def _connection_name(self, group: list[str]) -> str | None:
        """A junction's name is authored, never derived: it is what its
        symbols write as `connection`, or, where a junction is one symbol, that
        symbol's own name. `None` where the component declares no transits and
        so has nothing to name."""
        declared = sorted({self.symbols[s].connection for s in group} - {""})
        if len(declared) > 1:
            raise ValueError(
                f"drawing '{self.name}': {declared} are one connection, drawn"
                f" from {group} with no block between them — keep one of the"
                f" names and write it on every one of those symbols"
            )
        if declared:
            return declared[0]

        declaring = [s for s in group if self.symbols[s].transits]
        if len(declaring) > 1:
            raise ValueError(
                f"drawing '{self.name}': the junction drawn from {declaring}"
                f" is unnamed — write `connection` on its symbols"
            )
        return declaring[0] if declaring else None

    # --- pass 2: walking symbol transits gives the connection transits -----

    def _walks(self, joins: dict[str, list[str]]) -> list[Walk]:
        """Every way from one block end to another, with the symbol transits
        it took. Each is found twice, once from each end; the pair of ends and
        the set of transits identify it, so the second sighting is dropped."""
        found: dict[tuple[frozenset[str], frozenset[Use]], Walk] = {}

        def walk(node: str, came_from: str, used: tuple[Use, ...], start: str) -> None:
            name, _, pin = node.partition(".")
            symbol = self.symbols[name]

            if symbol.kind == "block":
                ends = cast(tuple[str, str], tuple(sorted((start, node))))
                found.setdefault((frozenset(ends), frozenset(used)), (ends, used))
                return
            if symbol.kind == "terminal":
                return

            if symbol.kind in _JOINERS:
                # A joiner has no transits of its own, but two ways through it
                # share the same track, so record the visit for pass 3.
                step = (name, "")
                if step in used:
                    return
                for other in joins[node]:
                    if other != came_from:
                        walk(other, node, used + (step,), start)
                return

            for local, (a, b) in symbol.transits.items():
                if pin not in (a, b):
                    continue
                step = (name, local)
                if step in used:
                    continue
                far = f"{name}.{b if pin == a else a}"
                for other in joins[far]:
                    walk(other, far, used + (step,), start)

        for block in self._of_kind("block"):
            for pin in block.pins:
                start = f"{block.name}.{pin}"
                for node in joins[start]:
                    walk(node, start, (), start)
        return list(found.values())

    # --- pass 3: composing symbol concurrency ------------------------------

    def _blocking(self, one: tuple[Use, ...], two: tuple[Use, ...]) -> list[str]:
        """The symbols two ways share that stop them running together.

        A symbol blocks unless it declares every pair of its transits the two
        ways take through it concurrent. A symbol transit is self-exclusive,
        so sharing one is always a conflict. Empty means they run together.
        """
        taken: tuple[dict[str, set[str]], dict[str, set[str]]] = (
            defaultdict(set),
            defaultdict(set),
        )
        for side, used in zip(taken, (one, two)):
            for symbol, local in used:
                side[symbol].add(local)
        return sorted(
            symbol
            for symbol in taken[0].keys() & taken[1].keys()
            if any(
                frozenset((here, there)) not in self.symbols[symbol].concurrent
                for here in taken[0][symbol]
                for there in taken[1][symbol]
            )
        )

    def _concurrent(self, one: tuple[Use, ...], two: tuple[Use, ...]) -> bool:
        return not self._blocking(one, two)

    def _connection(self, named: dict[str, Walk]) -> dict[str, Any]:
        concurrent = [
            sorted((one, two))
            for i, one in enumerate(sorted(named))
            for two in sorted(named)[i + 1 :]
            if self._concurrent(named[one][1], named[two][1])
        ]
        return {
            "transits": {name: list(named[name][0]) for name in sorted(named)},
            **({"concurrent": sorted(concurrent)} if concurrent else {}),
        }

    def _transit_name(
        self, where: str, ends: tuple[str, str], used: tuple[Use, ...]
    ) -> str:
        """A derived name is a pure function of the two block ends, so moving
        a symbol never renames a transit. A symbol transit written with a name
        overrides it: that is how the generic connection symbol passes its
        hand-picked names through unchanged, and how a junction drawn from real
        symbols keeps them — the name goes on the symbol transit the way
        through takes, so one symbol names every way that crosses it."""
        overrides = sorted(
            {
                self.symbols[name].names[local]
                for name, local in used
                if local in self.symbols[name].names
            }
        )
        if len(overrides) > 1:
            raise ValueError(
                f"{where}: transit {list(ends)} takes its name from several"
                f" symbol transits {overrides}"
            )
        if overrides:
            return overrides[0]
        return "__".join(end.replace(".", "_") for end in ends)

    def _of_kind(self, kind: str) -> list[Symbol]:
        return [
            self.symbols[name]
            for name in sorted(self.symbols)
            if self.symbols[name].kind == kind
        ]


def _wires_wanted(symbol: Symbol) -> int:
    """A free-standing bend joins two wires; every other pin joins one, the
    symbol itself being its second connection."""
    return 2 if symbol.kind == "pin" else 1


def _pair(joins: dict[str, list[str]], worn_by: list[str]) -> None:
    a, b = (f"{name}.P" for name in sorted(worn_by))
    joins[a].append(b)
    joins[b].append(a)


def _symbol(where: str, name: str, spec: Any) -> Symbol:
    as_mapping(spec, where)
    kind = spec.get("kind")
    placement = set(_PLACEMENT)
    _check_geometry(spec, where)
    if kind == "block":
        check_keys(spec, where, {"kind", "length"}, {"sensors"} | placement)
        for end, sensor in as_mapping(
            spec.get("sensors") or {}, f"{where}: sensors"
        ).items():
            if end not in PINS[kind]:
                raise ValueError(f"{where}: sensors names unknown end '{end}'")
            check_name(sensor, f"{where}: sensor")
        # Hardware ids are the drawing's alone: derivation drops them, so the
        # layout and SYSTEM.md's contracts never see them. A block has no name
        # but its key, which is what the canvas draws and what prefixes every
        # transit id; `label` belongs to a portal, where it pairs two mouths.
        return Symbol(
            name,
            kind,
            PINS[kind],
            length=check_length(spec["length"], where),
        )
    if kind in ("terminal", "pin"):
        check_keys(spec, where, {"kind"}, placement)
        return Symbol(name, kind, PINS[kind])
    if kind == "portal":
        check_keys(spec, where, {"kind", "label"}, placement)
        check_name(spec["label"], f"{where}: portal label")
        return Symbol(name, kind, PINS[kind], label=str(spec["label"]))
    if kind in LIBRARY:
        return _library_symbol(where, name, spec, kind)
    if kind == "connection":
        return _connection_symbol(where, name, spec)
    raise ValueError(f"{where}: unknown kind {kind!r}")


def _library_symbol(where: str, name: str, spec: Any, kind: str) -> Symbol:
    """A symbol of fixed geometry: its pins, its transits and its concurrency
    come from the library, so the drawing writes only the names it wants."""
    optional = {"names", "connection"} | _PLACEMENT
    if kind in POSITIONS:
        optional.add("addr")
    check_keys(spec, where, {"kind"}, optional)
    transits = LIBRARY[kind]

    names: dict[str, str] = {}
    for transit, authored in as_mapping(
        spec.get("names") or {}, f"{where}: names"
    ).items():
        if transit not in transits:
            raise ValueError(f"{where}: names unknown transit '{transit}'")
        check_name(authored, f"{where}: transit")
        names[transit] = str(authored)

    return Symbol(
        name,
        kind,
        PINS[kind],
        dict(transits),
        names=names,
        connection=_connection_of(where, spec),
        # Nothing checks an address, so nothing but the yaml's own quoting
        # separates the accessory number 31 from the string "31" (ADR-0022).
        addr=str(spec.get("addr", "")),
    )


def _connection_of(where: str, spec: Any) -> str:
    """The junction a symbol says it belongs to, where it says so."""
    if "connection" not in spec:
        return ""
    check_name(spec["connection"], f"{where}: connection")
    return str(spec["connection"])


def _connection_symbol(where: str, name: str, spec: Any) -> Symbol:
    check_keys(
        spec,
        where,
        {"kind", "pins", "transits"},
        {"concurrent", "connection"} | _PLACEMENT,
    )

    pins: list[str] = []
    raw_pins = spec["pins"]
    if not isinstance(raw_pins, list) or not cast(list[Any], raw_pins):
        raise ValueError(f"{where}: pins must be a non-empty list")
    for pin in cast(list[Any], raw_pins):
        check_name(pin, f"{where}: pin")
        if pin in pins:
            raise ValueError(f"{where}: duplicate pin '{pin}'")
        pins.append(str(pin))

    raw_transits = spec["transits"]
    names_transits = isinstance(raw_transits, dict)
    if names_transits:
        declared = list(cast(dict[str, Any], raw_transits).items())
        for transit, _ in declared:
            check_name(transit, f"{where}: transit")
    elif isinstance(raw_transits, list):
        declared = [
            (str(i), pair) for i, pair in enumerate(cast(list[Any], raw_transits))
        ]
    else:
        raise TypeError(
            f"{where}: transits must be a mapping of names to pin pairs, or a"
            f" list of pin pairs to take derived names"
        )

    transits: dict[str, tuple[str, str]] = {}
    for transit, raw_pair in declared:
        pair = _pin_pair(raw_pair, f"{where}: transit '{transit}'")
        for pin in pair:
            if pin not in pins:
                raise ValueError(
                    f"{where}: transit '{transit}' names unknown pin '{pin}'"
                )
        transits[transit] = pair

    if "concurrent" in spec and not names_transits:
        raise ValueError(f"{where}: concurrent needs named transits")
    concurrent = check_concurrent(spec.get("concurrent"), transits, where)

    return Symbol(
        name,
        "connection",
        tuple(pins),
        transits,
        concurrent,
        names={transit: transit for transit in transits} if names_transits else {},
        connection=_connection_of(where, spec),
    )


def _check_geometry(spec: Any, where: str) -> None:
    if "at" in spec:
        at = spec["at"]
        if not isinstance(at, list) or [
            n for n in cast(list[Any], at) if not isinstance(n, int)
        ]:
            raise ValueError(f"{where}: at must be two integers, got {at!r}")
        if len(cast(list[Any], at)) != 2:
            raise ValueError(f"{where}: at must be two integers, got {at!r}")
    if "rot" in spec and spec["rot"] not in ROTATIONS:
        raise ValueError(f"{where}: rot must be one of {list(ROTATIONS)}")
    if "flip" in spec and not isinstance(spec["flip"], bool):
        raise ValueError(f"{where}: flip must be true or false")


def _wire(raw: Any, where: str) -> tuple[Any, str]:
    """A wire's pins, and the connection name it carries where it has one. The
    pair form is the usual one; the mapping form is for a wire that joins two
    blocks, which is a connection and so needs a name."""
    if not isinstance(raw, dict):
        return raw, ""
    spec = cast(dict[str, Any], raw)
    check_keys(spec, where, {"pins", "connection"})
    check_name(spec["connection"], f"{where}: connection")
    return spec["pins"], str(spec["connection"])


def _pin_pair(raw: Any, where: str) -> tuple[str, str]:
    """The two distinct pins a wire or a symbol transit joins."""
    pair = [str(pin) for pin in cast(list[Any], raw)] if isinstance(raw, list) else []
    if len(pair) != 2 or pair[0] == pair[1]:
        raise ValueError(f"{where} must join two distinct pins, got {raw!r}")
    return pair[0], pair[1]


def _check_pin(node: str, symbols: dict[str, Symbol], where: str) -> str:
    symbol, dot, pin = node.partition(".")
    if not dot or symbol not in symbols or pin not in symbols[symbol].pins:
        raise ValueError(f"{where}: unknown pin '{node}'")
    return node
