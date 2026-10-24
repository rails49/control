"""Asset store: the CRUD contract over the YAML binding.

Two coarse document types (ADR-0010) keyed by name — `crossover-yard` for
drawings, layout-qualified `crossover-yard/meet` for scenarios, with a
railroad's **roster** beside its drawing under the same name and the
installation's **catalogue** beside them both. Verbs:
``get``, ``put`` (whole-document create-or-replace), ``delete``, ``list``.
Validation — schema and referential integrity — runs at ``put`` and again
at ``get``, because the YAML files are hand-authored and never passed
through ``put``. A ``get`` never returns an invalid document; all
derivation (conflict matrix, terminals, arrival-end expansion, fit
pruning) stays consumer-side. What a document may *hold* is checked at the
read as well, these files being hand-written in a language that can say more
than a document can (`_read`, #641).

A layout is not a document type: ``get`` derives it from the drawing
(ADR-0015, DRAWING.md) and hands it to the validator, so a railroad has
exactly one committed description.

The **roster** is a document of the railroad rather than of a run (ADR-0039),
so a scenario names trains from it and states no length of its own: one train
has one length however many scenarios place it. ``_load_scenario`` joins the
two, which is why a :class:`~tc49.lib.scenario.Scenario` carries placement
alone and the length comes back on the :class:`~tc49.lib.roster.Roster`.

The **script** is the railroad's as well, and the one document here that is
not YAML: the text a translator loads to speak to that railroad's command
station (ADR-0043). It is kept and never read — nothing here parses, compiles
or runs it, so what the text means stays the translator's.

The **catalogue** is the installation's and belongs to no railroad, a model
being what a product is (ADR-0045); a roster is read against it, since a car
names a model and is complete only once merged onto one. Both stock documents
are validated in :mod:`tc49.lib.stock`. A model's **photo** is the one thing
here that is not a document: the JPEG beside its document, kept because the
file is there and named by nothing inside it (#626).

The **loaded railroad** is the installation's as well: which railroad the
layout binding last loaded, recorded so that it starts on that one after a
reboot, the broker keeping nothing across a restart (ADR-0072 decision 5).
"""

import math
import re
import shutil
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

LOADED = "loaded.yaml"
"""The file at the store root recording which railroad is loaded."""

_TIMESTAMP = "tag:yaml.org,2002:timestamp"
"""The one implicit tag this store's reader does not resolve (`_Reader`)."""

_BOOL = "tag:yaml.org,2002:bool"
"""The implicit tag this store's reader resolves from fewer words (`_Reader`)."""


class _Reader(yaml.SafeLoader):
    """`yaml.SafeLoader` with the date dropped out of it, and a boolean read
    from `true` and `false` alone.

    **A date is text.** `bought: 2026-10-05` in a field nothing here reads is
    the string somebody typed, not a `datetime.date`: a document is handed on
    as JSON by every face of this store, and a date is a value JSON cannot
    carry, so an unquoted one in a hand-written catalogue entry answered
    `GET /catalogue/<model>` — and `GET /catalogue` with it — by dropping the
    connection (#641). Quoting it would be the person's workaround for a bug
    of ours, and a `date` is nothing this software has a use for anyway: what
    reads a model's fields is the screen that shows them.

    Dropping the resolver rather than reading the document and converting
    after, so the value never exists: a conversion would have to find dates
    at every depth of two document types and would turn `!!timestamp` into
    text as well, where an explicit tag asks for exactly what
    `_check_values` refuses.

    **`on`, `off`, `yes` and `no` are text.** YAML 1.1 reads them unquoted as
    booleans; YAML 1.2, which `yamlfile` writes in, reads them as words and
    writes them unquoted. A toggle saved with `on: on, off: off` came back
    with keys `True` and `False` and its drawing was refused (#945).
    """


_Reader.yaml_implicit_resolvers = {
    first: [
        (tag, pattern) for tag, pattern in resolvers if tag not in (_TIMESTAMP, _BOOL)
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Reader.add_implicit_resolver(  # pyright: ignore[reportUnknownMemberType]
    _BOOL, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)


def _check_values(value: Any, path: Path, field: str = "") -> None:
    """Refuse a value no document can hold, naming the file and the field.

    A document holds text, numbers, booleans, nothing, lists and mappings —
    what these YAML files are written in and what every binding of the CRUD
    contract carries. YAML's own vocabulary reaches further: `!!binary` is
    `bytes` and `!!set` is a `set`, and a file hand-edited to hold one is
    refused here, the way a model that does not validate is refused naming the
    model.

    **A number is a finite number.** `.inf`, `-.inf` and `.nan` resolve to a
    `float`, so they are the far end of YAML's vocabulary that arrives as a
    type a document does hold; `json.dumps` writes them as the tokens
    `Infinity`, `-Infinity` and `NaN`, which a browser's `JSON.parse` rejects,
    so `bought: .inf` in one hand-edited catalogue file blanked the catalogue
    screen the way an unquoted date did (#649). Refused rather than taken off
    the reader the way the date is (`_Reader`): the float resolver is the one
    that reads `weight: 1.5`, and a document holds that.

    Refused at the read rather than where a face serialises, because this is
    where such a value comes into being: `handle` turns the refusal into the
    400 a wrong document already gets, and no reply on that face is ever built
    out of something it cannot send (#641). A photo is the one thing the store
    keeps that is not a document, and it is a file beside one rather than a
    field in it (#626).
    """
    if isinstance(value, dict):
        for key, held in cast(dict[Any, Any], value).items():
            where = f"{field}.{key}" if field else str(key)
            _check_values(key, path, where)
            _check_values(held, path, where)
        return
    if isinstance(value, list):
        for index, held in enumerate(cast(list[Any], value)):
            _check_values(held, path, f"{field}[{index}]")
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            f"{path.name}: '{field}' is {value}, which is not a finite number"
            " and so not something a document can hold"
        )
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    raise ValueError(
        f"{path.name}: '{field}' is a {type(value).__name__}, which is not"
        " something a document can hold"
    )


def _field(held: Any, key: str) -> Any:
    """What a document as written holds under `key`, and `None` where it is
    not the mapping that would hold it — the read a roster gets when it is
    asked what it uses rather than validated."""
    return cast(dict[str, Any], held).get(key) if isinstance(held, dict) else None


def _items(section: Any) -> list[tuple[Any, Any]]:
    """A roster section's entries as written, and none where it is not the
    mapping a roster's `cars` and `trains` are."""
    return (
        list(cast(dict[Any, Any], section).items()) if isinstance(section, dict) else []
    )


def _entries(listed: Any) -> list[Any]:
    """A train's `cars` as written, and none where it is not a list."""
    return cast(list[Any], listed) if isinstance(listed, list) else []


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

    def script(self, name: str) -> str:
        """One railroad's translator script, as the text it is.

        A document of the railroad like its roster, filed beside the drawing:
        what the translator has to say to this railroad's command station is
        the railroad's own, and one railroad has one of them (ADR-0043).

        A railroad with no script file raises, where a roster answers empty:
        owning no stock is a state the screen that writes the first car has to
        read, and a translator handed nothing has nothing to run and has to
        hear so.

        Not parsed, compiled or run here. The store keeps what it is given —
        what the text means is the translator's, and whether it compiles is
        settled by the face that writes it, so a script this store cannot make
        sense of is still a script it can hand back for somebody to fix.
        """
        return self._script_path(name).read_bytes().decode()

    def put_script(self, text: str, name: str) -> None:
        """Create or replace one railroad's translator script.

        Bytes rather than `write_text`, and `read_bytes` on the way out: the
        text is handed back as it arrived, down to a line ending, because it
        is source somebody wrote and this store is not the author of it.
        """
        path = self._script_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())

    def copy(self, source: str, to: str) -> None:
        """Copy railroad `source`'s documents under the name `to`: its drawing,
        its roster where it has one, and its script where it has one, each
        naming itself `to` (ADR-0072).

        Every document is read and validated before anything is written, so a
        refusal leaves the store as it was. A `source` with no drawing raises
        `FileNotFoundError`, and a `to` any of whose three files exists raises
        `FileExistsError` — a roster or a script alone is somebody's railroad
        already, and a copy laid over it would mix two.

        Scenarios are the harness's and the catalogue is every railroad's, so
        neither is copied. Each document's file is taken as it is before the
        one naming `to` is merged onto it, so the copy keeps the prose its
        source was written with (ADR-0018).
        """
        drawing = self.drawing(source)
        roster = (
            self.roster_document(source) if self._roster_path(source).exists() else None
        )
        script = self.script(source) if self._script_path(source).exists() else None
        taken = (self._drawing_path(to), self._roster_path(to), self._script_path(to))
        if any(path.exists() for path in taken):
            raise FileExistsError(f"'{to}' is already a railroad")
        shutil.copyfile(self._drawing_path(source), self._drawing_path(to))
        self.put({**drawing, "drawing": to})
        if roster is not None:
            shutil.copyfile(self._roster_path(source), self._roster_path(to))
            self.put_roster({**roster, "roster": to}, to)
        if script is not None:
            self.put_script(script, to)

    def loaded(self) -> str:
        """The railroad the layout binding last loaded, and `""` where
        nothing records one: a fresh box, or one that has never loaded a
        railroad. Not checked against the drawings — the binding that wrote
        the name is the one that reads it, and says so if it is gone."""
        path = self._root / LOADED
        if not path.exists():
            return ""
        doc = self._read(path)
        railroad = (
            cast(dict[str, Any], doc).get("railroad") if isinstance(doc, dict) else None
        )
        if not isinstance(railroad, str):
            raise TypeError(f"{LOADED}: 'railroad' is the railroad's name, as text")
        return railroad

    def put_loaded(self, name: str) -> None:
        """Record `name` as the railroad loaded, replacing what was."""
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / LOADED).write_text(yaml.safe_dump({"railroad": name}))

    def catalogue(self) -> dict[str, Model]:
        """The models this installation knows, by name.

        Beside `layouts/` rather than under it: a model is what a product is,
        and a product does not become a different product on another layout,
        so every railroad reads the same ones (GLOSSARY.md, **Catalogue**). An
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

        A name another model already has is refused: the key tells the files
        apart, and the name is how a person tells the models apart (#975). A
        sibling that does not validate has no name to collide with, and does
        not stand in the way of this save.
        """
        model = stock.validate_model(doc, name)
        for other, path in self._model_paths().items():
            if other == name:
                continue
            try:
                taken = stock.validate_model(self._read(path), other).name
            except (ValueError, TypeError, yaml.YAMLError):
                continue
            if taken == model.name:
                raise ValueError(f"there is already a model '{model.name}'")
        path = self._model_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        yamlfile.save(path, doc)

    def delete_model(self, name: str) -> None:
        """Delete one model and its photo, where no roster uses it (#976).

        Every roster in the store is asked, whichever railroad is loaded: a
        railroad not running today is still one somebody will load, and a car
        naming a model that is gone is a roster that no longer reads. Each is
        read as written rather than validated, so a half-made roster is not
        where a deletion slips through. Refused with every place that names
        the model, so a person knows what to change; a missing model raises
        `FileNotFoundError`.
        """
        path = self._model_path(name)
        doc = self._read(path)
        users = [
            f"railroad '{railroad}': {', '.join(places)}"
            for railroad, places in self._uses(name).items()
        ]
        if users:
            shown = _field(doc, "name") or name
            raise ValueError(f"model '{shown}' is used by {'; '.join(users)}")
        path.unlink()
        self._photo_path(name).unlink(missing_ok=True)

    def _uses(self, model: str) -> dict[str, list[str]]:
        """Where each roster names `model`, by railroad: a car whose `model:`
        is it, or a train with an entry whose `model:` is it. Read as written,
        so whatever shape a hand-edited roster is in, what names the model
        is found."""
        uses: dict[str, list[str]] = {}
        for path in sorted((self._root / "layouts").glob("*.roster.yaml")):
            doc = self._read(path)
            places = [
                f"car '{car}'"
                for car, spec in _items(_field(doc, "cars"))
                if _field(spec, "model") == model
            ] + [
                f"train '{train}'"
                for train, spec in _items(_field(doc, "trains"))
                if any(
                    _field(entry, "model") == model
                    for entry in _entries(_field(spec, "cars"))
                )
            ]
            if places:
                uses[path.name.removesuffix(".roster.yaml")] = places
        return uses

    def photo(self, name: str) -> bytes:
        """One model's photo, as the bytes it was given.

        Kept as `catalogue/<name>.jpg` beside the model's document, so a
        model's name is the whole of what finds it and the picture is backed
        up with the rest of the store. The document does not name the file:
        the photo exists when the file does, which is what keeps a model
        nobody has photographed from carrying a field saying so (#626).

        A model with no photo raises, the way a railroad with no script does:
        there is nothing to show, and the surface that would show it has to
        hear that rather than draw an empty frame.
        """
        return self._photo_path(name).read_bytes()

    def put_photo(self, jpeg: bytes, name: str) -> None:
        """Create or replace one model's photo, byte for byte.

        Refused where the installation has no model `<name>`: the photo hangs
        off the document, and a file beside one that is not there is a photo
        of nothing that no screen would ever read. Refused too where the bytes
        do not open as a JPEG does, the file being named `.jpg` and what reads
        it reading the name. The magic number is the whole of the check —
        scaling, cropping and what the picture shows stay the camera's and the
        person's, and this store re-encodes nothing.
        """
        if not self._model_path(name).exists():
            raise ValueError(f"no model '{name}' to hang a photo on")
        if not jpeg.startswith(b"\xff\xd8\xff"):
            raise ValueError(f"photo '{name}': the bytes do not open as a JPEG")
        self._photo_path(name).write_bytes(jpeg)

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

    def _photo_path(self, name: str) -> Path:
        return self._root / "catalogue" / f"{name}.jpg"

    def _model_paths(self) -> dict[str, Path]:
        """The catalogue's files by the name each is filed under, which is
        its own. An installation with no `catalogue/` has none."""
        return {
            path.name.removesuffix(".yaml"): path
            for path in sorted((self._root / "catalogue").glob("*.yaml"))
        }

    def _roster_path(self, name: str) -> Path:
        return self._root / "layouts" / f"{name}.roster.yaml"

    def _script_path(self, name: str) -> Path:
        return self._root / "layouts" / f"{name}.script.py"

    def _scenario_path(self, name: str) -> Path:
        layout, _, scenario = name.partition("/")
        return self._root / "scenarios" / layout / f"{scenario}.scenario.yaml"

    def _read(self, path: Path) -> Any:
        """One of this store's YAML files, read as the document it is.

        The store's one reader, which is why both rules about what a document
        holds are here: the Python binding an app uses and the HTTP face the
        editor talks to read the same file through this, so neither can see a
        value the other cannot (#641).
        """
        doc: Any = yaml.load(path.read_text(), Loader=_Reader)
        _check_values(doc, path)
        return doc

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
