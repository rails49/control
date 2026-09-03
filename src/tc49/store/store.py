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
are validated in :mod:`tc49.store.stock`.
"""

from pathlib import Path
from typing import Any, cast

import yaml

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
from tc49.lib.roster import Model, Roster
from tc49.lib.scenario import RequestSpec, Scenario, TrainSpec
from tc49.store import stock, yamlfile
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
        roster = self.validate_roster(self._read(path))
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
        — the shelf a locomotive lives on — survives a save (`store.stock`).
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
        standing: dict[str, str | None] = {
            train: spec.at for train, spec in trains.items()
        }
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
