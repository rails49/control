"""Asset store: the CRUD contract over the milestone-1 YAML binding.

Two coarse document types (ADR-0010) keyed by name — `crossover-yard` for
drawings, layout-qualified `crossover-yard/meet` for scenarios, with a
railroad's **roster** beside its drawing under the same name. Verbs:
``get``, ``put`` (whole-document create-or-replace), ``delete``, ``list``.
Validation — schema and referential integrity — runs at ``put`` and again
at ``get``, because the YAML files are hand-authored and never passed
through ``put``. A ``get`` never returns an invalid document; all
derivation (conflict matrix, terminals, arrival-end expansion, fit
pruning) stays consumer-side.

A layout is not a document type: ``get`` derives it from the drawing
(ADR-0015, DRAWING.md) and hands it to the validator, so a railroad has
exactly one committed description.

The **roster** is a document of the railroad rather than of a run (ADR-0039),
so a scenario names trains from it and states no length of its own: one train
has one length however many scenarios place it. ``_load_scenario`` joins the
two, which is why a :class:`~tc49.lib.scenario.Scenario` carries placement
alone and the length comes back on the :class:`~tc49.lib.roster.Roster`.
"""

from pathlib import Path
from typing import Any, cast

import yaml

from tc49.lib.layout import (
    Layout,
    as_mapping,
    block_of,
    check_end,
    check_keys,
    check_length,
    check_name,
)
from tc49.lib.roster import Roster, Train
from tc49.lib.scenario import RequestSpec, Scenario, TrainSpec
from tc49.store import yamlfile
from tc49.store.drawing import Drawing


class AssetStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def drawing(self, name: str) -> dict[str, Any]:
        """The drawing document itself, which ``get`` derives away. The editor
        edits this, so it comes back as written, checked for schema but not
        for the pin rules: work in progress is readable."""
        doc = cast(dict[str, Any], self._read(self._drawing_path(name)))
        Drawing.from_document(doc)
        return doc

    def roster(self, name: str) -> Roster:
        """The trains a railroad owns (ADR-0039).

        A railroad with no roster file owns nothing yet, which is what a
        drawing made this morning is: nothing about a drawing implies a file
        beside it, and answering an empty roster says that, where a
        `FileNotFoundError` would say the railroad is missing. A scenario
        placing a train it does not name is refused where the train is named,
        which is where the mistake was made.
        """
        path = self._roster_path(name)
        if not path.exists():
            return Roster(name, {})
        roster = self.validate_roster(self._read(path))
        if roster.railroad != name:
            raise ValueError(f"roster '{name}': file names itself '{roster.railroad}'")
        return roster

    def get(self, name: str) -> Layout | Scenario:
        if "/" in name:
            return self._load_scenario(name)
        drawing = Drawing.from_document(self._read(self._drawing_path(name)))
        return Layout.from_document(drawing.derive())

    def scenarios(self) -> list[str]:
        """Every scenario there is, layout-qualified. `list` takes one layout
        because a scenario belongs to one; a panel joining a session picks
        from all of them and does not know the layout yet (ui/PANEL.md)."""
        paths = (self._root / "scenarios").glob("*/*.scenario.yaml")
        return sorted(
            f"{p.parent.name}/{p.name.removesuffix('.scenario.yaml')}" for p in paths
        )

    def list(self, layout: str | None = None) -> list[str]:
        if layout is None:
            drawings = (self._root / "layouts").glob("*.drawing.yaml")
            return sorted(p.name.removesuffix(".drawing.yaml") for p in drawings)
        paths = (self._root / "scenarios" / layout).glob("*.scenario.yaml")
        return sorted(
            f"{layout}/{p.name.removesuffix('.scenario.yaml')}" for p in paths
        )

    def put(self, doc: dict[str, Any]) -> None:
        if "scenario" in doc:
            scenario = self.validate_scenario(doc)
            path = self._scenario_path(f"{scenario.layout}/{scenario.name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(doc, sort_keys=False))
            return
        if "drawing" not in doc:
            raise ValueError(
                "document is neither a drawing nor a scenario — a layout is"
                " derived from a drawing, never stored"
            )
        # Schema only: a drawing with a dangling pin is work in progress
        # and is saved, though it will not derive (DRAWING.md).
        path = self._drawing_path(Drawing.from_document(doc).name)
        path.parent.mkdir(parents=True, exist_ok=True)
        yamlfile.save(path, doc)  # merge: the file keeps what it says

    def delete(self, name: str) -> None:
        if "/" in name:
            self._scenario_path(name).unlink()
            return
        self._drawing_path(name).unlink()

    def _drawing_path(self, name: str) -> Path:
        return self._root / "layouts" / f"{name}.drawing.yaml"

    def _roster_path(self, name: str) -> Path:
        return self._root / "layouts" / f"{name}.roster.yaml"

    def _scenario_path(self, name: str) -> Path:
        layout, _, scenario = name.partition("/")
        return self._root / "scenarios" / layout / f"{scenario}.scenario.yaml"

    def _read(self, path: Path) -> Any:
        return yaml.safe_load(path.read_text())

    def _load_scenario(self, name: str) -> Scenario:
        scenario = self.validate_scenario(self._read(self._scenario_path(name)))
        if f"{scenario.layout}/{scenario.name}" != name:
            raise ValueError(
                f"scenario '{name}': file names itself"
                f" '{scenario.layout}/{scenario.name}'"
            )
        return scenario

    def validate_roster(self, doc: Any) -> Roster:
        """Validate a roster document without storing it — the path a
        generated fixture takes, so it is checked exactly as a committed file
        is."""
        check_keys(doc, "roster document", {"roster", "trains"})
        railroad = doc["roster"]
        check_name(railroad, "roster's railroad")
        where = f"roster '{railroad}'"
        trains: dict[str, Train] = {}
        for train, spec in as_mapping(doc["trains"], f"{where}: trains").items():
            check_keys(spec, f"{where}: train '{train}'", {"length"})
            trains[train] = Train(check_length(spec["length"], f"{where}: '{train}'"))
        return Roster(railroad, trains)

    def validate_scenario(self, doc: Any) -> Scenario:
        """Validate a scenario document without storing it — the path a
        generated fixture takes, so it is checked exactly as a committed
        file is."""
        check_keys(
            doc, "scenario document", {"scenario", "layout", "trains", "requests"}
        )
        name, layout_id = doc["scenario"], doc["layout"]
        check_name(name, "scenario")
        check_name(layout_id, "scenario's layout")
        where = f"scenario '{name}'"
        try:
            layout = self.get(layout_id)
        except FileNotFoundError:
            raise ValueError(f"{where}: names unknown layout '{layout_id}'") from None
        assert isinstance(layout, Layout)

        roster = self.roster(layout_id)
        trains: dict[str, TrainSpec] = {}
        for train, spec in as_mapping(doc["trains"], f"{where}: trains").items():
            check_keys(spec, f"{where}: train '{train}'", {"at", "facing"})
            # A scenario places the railroad's trains and owns none of its
            # own: how long a train is belongs to the roster (ADR-0039), so a
            # name that is not on it is stock this railroad does not have.
            if train not in roster.trains:
                raise ValueError(
                    f"{where}: train '{train}' is not on the roster of"
                    f" '{layout_id}'"
                )
            at = spec["at"]
            if at not in layout.blocks:
                raise ValueError(
                    f"{where}: train '{train}' starts at unknown block '{at}'"
                )
            facing = spec["facing"]
            if facing not in ("A", "B"):
                raise ValueError(
                    f"{where}: train '{train}' facing must be 'A' or 'B',"
                    f" got {facing!r}"
                )
            # A placement is what every later request is composed from, so an
            # end no connection holds is a train that can never leave (#145).
            # A *request* may still state one — facing is a discipline, not an
            # invariant (ADR-0019), and file scenarios keep that freedom.
            if f"{at}.{facing}" not in layout.end_connection:
                raise ValueError(
                    f"{where}: train '{train}' faces end '{at}.{facing}',"
                    f" which no connection holds"
                )
            trains[train] = TrainSpec(at, facing)

        requests: list[RequestSpec] = []
        if not isinstance(doc["requests"], list):
            raise TypeError(f"{where}: requests must be a list")
        for i, spec in enumerate(cast(list[Any], doc["requests"])):
            here = f"{where}: request {i + 1}"
            check_keys(spec, here, {"train", "from", "to", "at"})
            train, depart, to, at = (
                str(spec["train"]),
                str(spec["from"]),
                spec["to"],
                spec["at"],
            )
            if train not in trains:
                raise ValueError(f"{here}: unknown train '{train}'")
            if not isinstance(at, int) or at < 0:
                raise ValueError(
                    f"{here}: 'at' must be a non-negative boundary, got {at!r}"
                )
            _check_departure_end(depart, layout, here)
            if not isinstance(to, list) or not to:
                raise ValueError(
                    f"{here}: 'to' must be a non-empty list of arrival ends"
                )
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
            requests.append(RequestSpec(train, depart, tuple(arrivals), at))

        return Scenario(name, layout_id, trains, tuple(requests))


def _check_departure_end(depart: str, layout: Layout, where: str) -> None:
    """Validate a 'from' entry: a full end, or a bare end letter for a
    chained request whose block is unknown at authoring time. Whether the
    train actually stands there is the dispatcher's admission check."""
    if depart not in ("A", "B"):
        check_end(depart, layout.blocks, where)
