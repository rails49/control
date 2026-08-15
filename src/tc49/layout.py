"""Layout: blocks, connections, transits, conflicts, terminal blocks.

The validated in-memory form of a layout document (LAYOUT.md). Validation
happens at construction — a mistyped end is a load-time error naming the
fault, never a ``KeyError`` mid-run. The conflict matrix is expanded from
``concurrent`` by inversion (ADR-0006): every pair of transits at a
connection conflicts unless declared, and transits are self-exclusive.
Terminal blocks are derived, never declared. Routing stays outside —
Layout is a data structure, not a policy.

The ``check_*`` helpers are shared with the scenario validation in
``store.py``.
"""

from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True)
class Connection:
    name: str
    transits: dict[str, tuple[str, str]]  # transit name -> unordered end pair
    concurrent: frozenset[frozenset[str]]  # declared exceptions, by transit name


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
            length = spec["length"]
            if not isinstance(length, int) or length <= 0:
                raise ValueError(
                    f"layout '{name}': block '{block}': length must be a"
                    f" positive integer, got {length!r}"
                )
            blocks[block] = length

        connections: dict[str, Connection] = {}
        end_owner: dict[str, str] = {}  # block end -> owning connection
        for conn, spec in as_mapping(
            doc["connections"], f"layout '{name}': connections"
        ).items():
            check_name(conn, f"layout '{name}': connection")
            where = f"layout '{name}': connection '{conn}'"
            check_keys(spec, where, {"transits"}, {"concurrent"})

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

            concurrent: set[frozenset[str]] = set()
            for raw_pair in spec.get("concurrent", []):
                if (
                    not isinstance(raw_pair, list)
                    or len(cast(list[Any], raw_pair)) != 2
                ):
                    raise ValueError(
                        f"{where}: concurrent entry must pair two distinct"
                        f" transits, got {raw_pair!r}"
                    )
                pair = [str(t) for t in cast(list[Any], raw_pair)]
                if pair[0] == pair[1]:
                    raise ValueError(
                        f"{where}: concurrent entry must pair two distinct"
                        f" transits, got {raw_pair!r}"
                    )
                for transit in pair:
                    if transit not in transits:
                        raise ValueError(
                            f"{where}: concurrent names unknown transit '{transit}'"
                        )
                concurrent.add(frozenset(pair))

            connections[conn] = Connection(conn, transits, frozenset(concurrent))

        terminals = frozenset(
            block
            for block in blocks
            if (f"{block}.A" in end_owner) != (f"{block}.B" in end_owner)
        )
        return cls(name, blocks, connections, terminals, end_owner)

    def transits_at(self, end: str) -> list[tuple[str, str]]:
        """The transits crossing `end`, as (qualified transit id, far end)."""
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


def check_end(end: Any, blocks: dict[str, int], where: str) -> str:
    """Validate an '<block>.<A|B>' end reference and return it as a string."""
    block, dot, letter = str(end).partition(".")
    if not dot or letter not in ("A", "B"):
        raise ValueError(f"{where}: end '{end}' must be '<block>.A' or '<block>.B'")
    if block not in blocks:
        raise ValueError(f"{where}: end '{end}' names unknown block '{block}'")
    return str(end)
