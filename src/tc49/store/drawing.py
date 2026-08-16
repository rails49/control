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
_CROSS = ("a1", "a2", "b1", "b2")
_THROUGH = {"a": ("a1", "a2"), "b": ("b1", "b2")}
_LIBRARY: dict[str, dict[str, tuple[str, str]]] = {
    "turnout": {"straight": ("toe", "straight"), "diverging": ("toe", "diverging")},
    "crossing": dict(_THROUGH),
    "single_slip": {**_THROUGH, "slip": ("a1", "b2")},
    "double_slip": {**_THROUGH, "slip_1": ("a1", "b2"), "slip_2": ("b1", "a2")},
}

# `pin` (a free-standing bend) and `portal` are joiners: they pass a wire
# through and derive to nothing.
_PINS: dict[str, tuple[str, ...]] = {
    "block": ("A", "B"),
    "terminal": ("P",),
    "portal": ("P",),
    "pin": ("P",),
    "turnout": ("toe", "straight", "diverging"),
    "crossing": _CROSS,
    "single_slip": _CROSS,
    "double_slip": _CROSS,
}
_JOINERS = frozenset({"pin", "portal"})

Use = tuple[str, str]  # a symbol and the local transit a walk took through it
Walk = tuple[tuple[str, str], tuple[Use, ...]]  # the block ends, and the way


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
    label: str = ""


@dataclass(frozen=True)
class Drawing:
    name: str
    symbols: dict[str, Symbol]
    wires: tuple[tuple[str, str], ...]  # pins, written '<symbol>.<pin>'
    units: str | None = None

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
        for raw in cast(list[Any], raw_wires):
            where = f"drawing '{name}': wire"
            a, b = _pin_pair(raw, where)
            wires.append((_check_pin(a, symbols, where), _check_pin(b, symbols, where)))

        return cls(name, symbols, tuple(wires), doc.get("units"))

    def derive(self) -> dict[str, Any]:
        """The layout document this drawing describes, in canonical order."""
        joins = self._joins()
        connection_of = self._connections(joins)

        grouped: dict[str, list[Walk]] = defaultdict(list)
        for ends, used in self._walks(joins):
            if ends[0] == ends[1]:
                raise ValueError(
                    f"drawing '{self.name}': the way out of '{ends[0]}' leads"
                    f" back into it — a transit joins two distinct block ends"
                )
            connection = connection_of[used[0][0]] if used else None
            if connection is None:
                raise ValueError(
                    f"drawing '{self.name}': the way from '{ends[0]}' to"
                    f" '{ends[1]}' runs through no connection symbol — blocks"
                    f" are joined through one"
                )
            grouped[connection].append((ends, used))

        return {
            "layout": self.name,
            **({} if self.units is None else {"units": self.units}),
            "blocks": {
                symbol.name: {"length": symbol.length}
                for symbol in self._of_kind("block")
            },
            "connections": {
                connection: self._connection(connection, grouped[connection])
                for connection in sorted(grouped)
            },
        }

    # --- the pin rules, checked at derivation, never at save ---------------

    def _joins(self) -> dict[str, list[str]]:
        """Every pin and what it joins: its wires, plus the pairing a portal
        wears. A joint is a joint however it is drawn, so portal pairs make
        the graph one connected whole before anything walks it."""
        portals: dict[str, list[str]] = defaultdict(list)
        for symbol in self._of_kind("portal"):
            portals[symbol.label].append(symbol.name)
        for label, worn_by in sorted(portals.items()):
            if len(worn_by) != 2:
                raise ValueError(
                    f"drawing '{self.name}': portal label '{label}' is worn by"
                    f" {len(worn_by)} portal(s) — a label pairs exactly two"
                )

        joins: dict[str, list[str]] = defaultdict(list)
        for a, b in self.wires:
            joins[a].append(b)
            joins[b].append(a)

        for symbol in self.symbols.values():
            wires = 2 if symbol.kind == "pin" else 1
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
            a, b = (f"{name}.P" for name in sorted(worn_by))
            joins[a].append(b)
            joins[b].append(a)
        return joins

    # --- pass 1: components of non-block symbols give the connections ------

    def _connections(self, joins: dict[str, list[str]]) -> dict[str, str | None]:
        """Each non-block symbol, mapped to the name of the connection its
        component derives — `None` where the component declares no transits
        and so has nothing to take a name from."""
        component: dict[str, str] = {
            symbol.name: symbol.name
            for symbol in self.symbols.values()
            if symbol.kind != "block"
        }

        def root(symbol: str) -> str:
            while component[symbol] != symbol:
                symbol = component[symbol] = component[component[symbol]]
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

        named: dict[str, str | None] = {}
        taken: dict[str, list[str]] = {}
        for group in members.values():
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

    def _connection_name(self, group: list[str]) -> str | None:
        """A junction's name is authored, never derived: it is what its
        symbols write as `connection`, or, where a junction is one symbol, that
        symbol's own name. `None` where the component declares no transits and
        so has nothing to name."""
        declared = sorted({self.symbols[s].connection for s in group} - {""})
        if len(declared) > 1:
            raise ValueError(
                f"drawing '{self.name}': the symbols {group} of one junction"
                f" name it {declared} — one junction takes one name"
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

    def _concurrent(self, one: tuple[Use, ...], two: tuple[Use, ...]) -> bool:
        """Two transits run concurrently only where every symbol they share
        declares the transits they take through it concurrent. A symbol
        transit is self-exclusive, so sharing one is always a conflict."""
        taken: tuple[dict[str, set[str]], dict[str, set[str]]] = (
            defaultdict(set),
            defaultdict(set),
        )
        for side, used in zip(taken, (one, two)):
            for symbol, local in used:
                side[symbol].add(local)
        for symbol in taken[0].keys() & taken[1].keys():
            concurrent = self.symbols[symbol].concurrent
            for here in taken[0][symbol]:
                for there in taken[1][symbol]:
                    if frozenset((here, there)) not in concurrent:
                        return False
        return True

    def _connection(self, connection: str, walks: list[Walk]) -> dict[str, Any]:
        where = f"drawing '{self.name}': connection '{connection}'"

        named: dict[str, Walk] = {}
        for ends, used in walks:
            name = self._transit_name(where, ends, used)
            if name in named:
                raise ValueError(
                    f"{where}: two transits named '{name}' — name one of them"
                    f" in the drawing"
                )
            named[name] = (ends, used)

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


def _symbol(where: str, name: str, spec: Any) -> Symbol:
    as_mapping(spec, where)
    kind = spec.get("kind")
    if kind == "block":
        check_keys(spec, where, {"kind", "length"}, {"sensors"})
        for end, sensor in as_mapping(
            spec.get("sensors") or {}, f"{where}: sensors"
        ).items():
            if end not in _PINS[kind]:
                raise ValueError(f"{where}: sensors names unknown end '{end}'")
            check_name(sensor, f"{where}: sensor")
        # Hardware ids are the drawing's alone: derivation drops them, so the
        # layout and SYSTEM.md's contracts never see them.
        return Symbol(
            name, kind, _PINS[kind], length=check_length(spec["length"], where)
        )
    if kind in ("terminal", "pin"):
        check_keys(spec, where, {"kind"})
        return Symbol(name, kind, _PINS[kind])
    if kind == "portal":
        check_keys(spec, where, {"kind", "label"})
        check_name(spec["label"], f"{where}: portal label")
        return Symbol(name, kind, _PINS[kind], label=str(spec["label"]))
    if kind in _LIBRARY:
        return _library_symbol(where, name, spec, kind)
    if kind == "connection":
        return _connection_symbol(where, name, spec)
    raise ValueError(f"{where}: unknown kind {kind!r}")


def _library_symbol(where: str, name: str, spec: Any, kind: str) -> Symbol:
    """A symbol of fixed geometry: its pins, its transits and its concurrency
    come from the library, so the drawing writes only the names it wants."""
    check_keys(spec, where, {"kind"}, {"names", "connection"})
    transits = _LIBRARY[kind]

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
        _PINS[kind],
        dict(transits),
        names=names,
        connection=_connection_of(where, spec),
    )


def _connection_of(where: str, spec: Any) -> str:
    """The junction a symbol says it belongs to, where it says so."""
    if "connection" not in spec:
        return ""
    check_name(spec["connection"], f"{where}: connection")
    return str(spec["connection"])


def _connection_symbol(where: str, name: str, spec: Any) -> Symbol:
    check_keys(spec, where, {"kind", "pins", "transits"}, {"concurrent", "connection"})

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
