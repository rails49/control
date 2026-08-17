"""Asset store: the CRUD contract over the milestone-1 YAML binding.

Two coarse document types (ADR-0010) keyed by name — `crossover-yard` for
drawings, layout-qualified `crossover-yard/meet` for scenarios. Verbs:
``get``, ``put`` (whole-document create-or-replace), ``delete``, ``list``.
Validation — schema and referential integrity — runs at ``put`` and again
at ``get``, because the YAML files are hand-authored and never passed
through ``put``. A ``get`` never returns an invalid document; all
derivation (conflict matrix, terminals, arrival-end expansion, fit
pruning) stays consumer-side.

A layout is not a document type: ``get`` derives it from the drawing
(ADR-0015, DRAWING.md) and hands it to the validator, so a railroad has
exactly one committed description.
"""

from pathlib import Path
from typing import Any, cast

import yaml

from tc49.lib.layout import (
    Layout,
    as_mapping,
    check_end,
    check_keys,
    check_length,
    check_name,
)
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

    def get(self, name: str) -> Layout | Scenario:
        if "/" in name:
            return self._load_scenario(name)
        drawing = Drawing.from_document(self._read(self._drawing_path(name)))
        return Layout.from_document(drawing.derive())

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

        trains: dict[str, TrainSpec] = {}
        for train, spec in as_mapping(doc["trains"], f"{where}: trains").items():
            check_keys(spec, f"{where}: train '{train}'", {"length", "at"})
            length = check_length(spec["length"], f"{where}: train '{train}'")
            at = spec["at"]
            if at not in layout.blocks:
                raise ValueError(
                    f"{where}: train '{train}' starts at unknown block '{at}'"
                )
            trains[train] = TrainSpec(length, at)

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
                    f"{here}: 'at' must be a non-negative tick, got {at!r}"
                )
            _check_departure_end(depart, layout, here)
            if not isinstance(to, list) or not to:
                raise ValueError(
                    f"{here}: 'to' must be a non-empty list of arrival ends"
                )
            arrivals: list[str] = []
            for entry in (str(e) for e in cast(list[Any], to)):
                block = entry.partition(".")[0]
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
