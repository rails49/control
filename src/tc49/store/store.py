"""Asset store: the CRUD contract over the milestone-1 YAML binding.

Two coarse document types (ADR-0010) keyed by name — `crossover-yard` for
drawings, layout-qualified `crossover-yard/meet` for scenarios, with a
railroad's **roster** beside its drawing under the same name and the
installation's **catalogue** beside them both. Verbs:
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

The **catalogue** is the installation's and belongs to no railroad, a model
being what a product is (ADR-0045); a roster is read against it, since a car
names a model and is complete only once merged onto one. Both stock documents
are validated in :mod:`tc49.lib.stock`.
"""

from pathlib import Path
from typing import Any, cast

import yaml

from tc49.lib import stock
from tc49.lib.layout import (
    Layout,
)
from tc49.lib.roster import Model, Roster
from tc49.lib.scenario import Scenario, named, validate_scenario
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
        """The stock a railroad owns: its cars, and the trains made up from
        them (ADR-0039, ADR-0045).

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
        return self._roster(self._read(path), name)

    def roster_document(self, name: str) -> dict[str, Any]:
        """One railroad's roster document itself, which `roster` validates
        away.

        As written, the way `drawing` and `model` are: this is what the stock
        screen edits, so an entry comes back in the shape the file has it — a
        car where the railroad has something to say about the item, its model
        where it has not (ADR-0061) — rather than the merged cars a train is
        derived from. Checked all the same, so what comes back is a roster.

        A railroad with no roster file owns nothing yet, and answers the empty
        document rather than a `FileNotFoundError`: owning nothing is an
        ordinary state, and the screen that writes the first car has to be
        able to read it to draw itself (`roster`).
        """
        path = self._roster_path(name)
        if not path.exists():
            return {"roster": name, "cars": {}, "trains": {}}
        doc = cast(dict[str, Any], self._read(path))
        self._roster(doc, name)
        return doc

    def put_roster(self, doc: dict[str, Any], name: str) -> None:
        """Create or replace one railroad's roster, validated before anything
        is written — a roster that does not validate leaves no file behind,
        and the file on disk is one a run can be built from.

        Whole-document, so a roster written without a car is that car removed:
        a roster is one document and there is no verb for a part of it.

        Merged into the file like a drawing rather than dumped over it: a
        roster says on itself which synthetic car stands for what and where a
        length came from, and a fresh dump would delete that (ADR-0018).
        """
        self._roster(doc, name)
        path = self._roster_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        yamlfile.save(path, doc)

    def _roster(self, doc: Any, name: str) -> Roster:
        """A roster document validated against the installation's catalogue
        and against the name it is filed under — the two checks a roster read
        or written under `name` gets, wherever it came from."""
        roster = self.validate_roster(doc)
        if roster.railroad != name:
            raise ValueError(f"roster '{name}': file names itself '{roster.railroad}'")
        return roster

    def catalogue(self) -> dict[str, Model]:
        """The models this installation knows, by name.

        Beside `layouts/` rather than under it: a model is what a product is,
        and a product does not become a different product on another layout,
        so every railroad reads the same ones (CONTEXT.md, **Catalogue**). An
        installation with no `catalogue/` directory knows none, which is a
        railroad whose stock is still written the old way and not a fault.
        """
        return {
            name: stock.validate_model(self._read(path), name)
            for name, path in self._model_paths().items()
        }

    def model(self, name: str) -> dict[str, Any]:
        """One model document itself, which `catalogue` validates away.

        As written, the way `drawing` is: the catalogue screen edits this
        file, and a model's document is the one place a field nothing reads
        — the shelf a locomotive lives on — survives a save (`lib/stock.py`).
        Checked all the same, so what comes back is a model.
        """
        doc = cast(dict[str, Any], self._read(self._model_path(name)))
        stock.validate_model(doc, name)
        return doc

    def models(self) -> dict[str, dict[str, Any]]:
        """Every model document as written, by name: `catalogue` unvalidated
        away, for the screen that edits them rather than the roster that
        reads against them."""
        return {name: self.model(name) for name in self._model_paths()}

    def put_model(self, doc: dict[str, Any], name: str) -> None:
        """Create or replace one model, validated before anything is written
        — a document that does not validate leaves no file behind, and a
        catalogue on disk is one a roster can be read against.

        Merged into the file like a drawing rather than dumped over it: a
        catalogue entry is hand-written and says on itself where the length
        was measured (`catalogue/README.md`), and a fresh dump would delete
        that (ADR-0018).
        """
        stock.validate_model(doc, name)
        path = self._model_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        yamlfile.save(path, doc)

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

    def _model_path(self, name: str) -> Path:
        return self._root / "catalogue" / f"{name}.yaml"

    def _model_paths(self) -> dict[str, Path]:
        """The catalogue's files by the name each is filed under, which is
        its own. An installation with no `catalogue/` has none."""
        return {
            path.name.removesuffix(".yaml"): path
            for path in sorted((self._root / "catalogue").glob("*.yaml"))
        }

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
        is. Against the catalogue, because a car naming a model the
        installation does not have is a car with no length."""
        return stock.validate_roster(doc, self.catalogue())

    def validate_scenario(self, doc: Any) -> Scenario:
        """Validate a scenario document without storing it — the path a
        generated fixture takes, so it is checked exactly as a committed
        file is.

        The store's part is the two documents the rule needs and cannot hold:
        the railroad the scenario names, and that railroad's roster. The rule
        itself is `lib`'s, where a reader that has the documents already can
        reach it without a directory (ADR-0013, #494).
        """
        name, layout_id = named(doc)
        try:
            layout = self.get(layout_id)
        except FileNotFoundError:
            raise ValueError(
                f"scenario '{name}': names unknown layout '{layout_id}'"
            ) from None
        assert isinstance(layout, Layout)
        return validate_scenario(doc, layout, self.roster(layout_id))
