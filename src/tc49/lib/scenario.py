"""The scenario document: placement and requests.

One of the coarse document types of ADR-0010, alongside
:class:`~tc49.lib.layout.Layout` and :class:`~tc49.lib.roster.Roster`. The
types live here rather than in the store because they are the shared
vocabulary every app reads; the store owns the binding that reads one off
disk.

**The validation is here too, and takes what it needs**, which is the reason
`lib/stock.py` gives for the roster's: what validates a document is what
reads one, and a reader in its own process has the document off the store's
HTTP face and cannot import the store to make sense of it (ADR-0013,
ADR-0059 decision 5). A scenario is only complete against two other
documents — the railroad it places trains on and the roster those trains are
on — so both are passed in, exactly as a car is only complete against the
catalogue. Fetching them instead is what made the rule reachable only through
a temp directory with a drawing and a roster copied into it (#494).

A scenario says where the railroad's trains **start**, not what they are: the
trains themselves are the railroad's roster and a train's length is written
there (ADR-0039). A scenario placing no train at all is a run that comes up
with an empty layout, which is an ordinary cold start rather than a fault.
"""

from dataclasses import dataclass
from typing import Any, cast

from tc49.lib.layout import (
    FACINGS,
    Layout,
    as_mapping,
    block_of,
    check_end,
    check_keys,
    check_name,
    facing_ends,
)
from tc49.lib.roster import Roster


@dataclass(frozen=True)
class TrainSpec:
    """Where a scenario stands one of its railroad's trains. The train is the
    roster's and so is its length; this is the placement alone."""

    at: str  # starting block
    facing: str  # 'A-to-B' or 'B-to-A': the run across `at` it would make


@dataclass(frozen=True)
class RequestSpec:
    train: str
    depart: str  # '<block>.<end>', or a bare end letter for chained requests
    arrivals: tuple[str, ...]  # arrival ends: '<block>.<end>' or bare '<block>'


@dataclass(frozen=True)
class Scenario:
    name: str
    layout: str
    trains: dict[str, TrainSpec]
    requests: tuple[RequestSpec, ...]


def named(doc: Any) -> tuple[str, str]:
    """A scenario document's own name and the railroad it places trains on,
    both checked as names before either is used.

    Read on its own because the store needs the railroad to know which two
    documents to fetch, and the validation below needs the name to say where
    a refusal is. One statement of the document's outermost shape, called
    twice rather than written twice.
    """
    check_keys(doc, "scenario document", {"scenario", "layout", "trains", "requests"})
    name, layout_id = doc["scenario"], doc["layout"]
    check_name(name, "scenario")
    check_name(layout_id, "scenario's layout")
    return name, layout_id


def validate_scenario(doc: Any, layout: Layout, roster: Roster) -> Scenario:
    """A scenario document, against the railroad it names and that railroad's
    stock.

    Both are passed in because a scenario is only complete against them: a
    train it places is the roster's and a block it places one in is the
    layout's, and neither is a fact this document holds. The caller that has
    them is whoever read the document — the store from disk, a generator from
    memory — and this rule is the same rule either way.
    """
    name, layout_id = named(doc)
    where = f"scenario '{name}'"

    trains: dict[str, TrainSpec] = {}
    for train, spec in as_mapping(doc["trains"], f"{where}: trains").items():
        check_keys(spec, f"{where}: train '{train}'", {"at", "facing"})
        # A scenario places the railroad's trains and owns none of its
        # own: how long a train is belongs to the roster (ADR-0039), so a
        # name that is not on it is stock this railroad does not have.
        if train not in roster.trains:
            raise ValueError(
                f"{where}: train '{train}' is not on the roster of '{layout_id}'"
            )
        at = spec["at"]
        if at not in layout.blocks:
            raise ValueError(f"{where}: train '{train}' starts at unknown block '{at}'")
        facing = spec["facing"]
        # The end letter this once was is refused rather than read: one
        # vocabulary, and a document written for an older build says
        # something the new one would take the other way round (#241).
        if facing not in FACINGS:
            raise ValueError(
                f"{where}: train '{train}' facing must be"
                f" {' or '.join(repr(one) for one in FACINGS)},"
                f" got {facing!r}"
            )
        # A placement is what every later request is composed from, so an
        # end no connection holds is a train that can never leave (#145).
        # A *request* may still state one — facing is a discipline, not an
        # invariant (ADR-0019), and file scenarios keep that freedom.
        nose = facing_ends(f"{at}.{facing}")[1]
        if nose not in layout.end_connection:
            raise ValueError(
                f"{where}: train '{train}' faces end '{nose}',"
                f" which no connection holds"
            )
        trains[train] = TrainSpec(at, facing)

    requests: list[RequestSpec] = []
    if not isinstance(doc["requests"], list):
        raise TypeError(f"{where}: requests must be a list")
    # train -> the block the file leaves it in ahead of its next working,
    # or None where the file does not fix one. The placement to begin
    # with; after a working, its arrival block where every arrival end
    # names one, and otherwise a dispatcher choice among them.
    standing: dict[str, str | None] = {train: spec.at for train, spec in trains.items()}
    for i, spec in enumerate(cast(list[Any], doc["requests"])):
        here = f"{where}: request {i + 1}"
        check_keys(spec, here, {"train", "from", "to"})
        train, depart, to = (
            str(spec["train"]),
            str(spec["from"]),
            spec["to"],
        )
        if train not in trains:
            raise ValueError(f"{here}: unknown train '{train}'")
        _check_departure_end(depart, layout, here)
        _check_departure_block(depart, standing[train], here)
        if not isinstance(to, list) or not to:
            raise ValueError(f"{here}: 'to' must be a non-empty list of arrival ends")
        arrivals: list[str] = []
        for entry in (str(e) for e in cast(list[Any], to)):
            block = block_of(entry)
            if block not in layout.blocks:
                raise ValueError(
                    f"{here}: arrival '{entry}' names unknown block '{block}'"
                )
            if "." in entry:
                check_end(entry, layout.blocks, here)
            arrivals.append(entry)
        blocks = {block_of(entry) for entry in arrivals}
        standing[train] = blocks.pop() if len(blocks) == 1 else None
        requests.append(RequestSpec(train, depart, tuple(arrivals)))

    return Scenario(name, layout_id, trains, tuple(requests))


def _check_departure_end(depart: str, layout: Layout, where: str) -> None:
    """Validate a 'from' entry: a full end, or a bare end letter for a
    chained request whose block is unknown at authoring time."""
    if depart not in ("A", "B"):
        check_end(depart, layout.blocks, where)


def _check_departure_block(depart: str, standing: str | None, where: str) -> None:
    """A stated departure block must be the block the file leaves the train
    in, and a working the file fixes no block for must state none.

    This is where an authoring slip is caught, because nothing downstream
    catches it: at run time a stated block is not a routing input but a hint,
    and the dispatcher corrects it from the route it chose itself (#135,
    DISPATCH.md) — a panel composes one against a train it has drawn mid-move,
    and correcting it is the working the operator asked for. A file is written
    ahead of the run, where the same disagreement is a mistake and a silently
    different experiment (LAYOUT.md). Only the block is judged: which end the
    train leaves by is scheduler discipline, not a fact the layout holds
    (ADR-0019).
    """
    if "." not in depart:  # a bare end letter states no block to disagree
        return
    block = block_of(depart)
    if standing is None:
        raise ValueError(
            f"{where}: departs '{block}', but where the train stands is a"
            " dispatcher choice among the previous working's arrival ends —"
            " write a bare end letter"
        )
    if block != standing:
        raise ValueError(
            f"{where}: departs '{block}', but the train stands in '{standing}'"
        )
