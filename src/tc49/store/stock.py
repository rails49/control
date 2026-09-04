"""The two stock documents: a catalogue's models, and a railroad's roster.

`catalogue/<model>.yaml` is one file per model, shared between railroads — a
product does not become a different product on another layout, so the
catalogue sits outside `layouts/` and every railroad reads the same models
(CONTEXT.md, **Catalogue**). `layouts/<railroad>.roster.yaml` keeps its path
and its name and changes referent: the cars the railroad owns, with the trains
made up from them beside (ADR-0045).

**Unknown keys are ignored, not refused**, in both documents and at every
level, which is the opposite of what the drawing and the scenario do. The
difference is that stock is a person's own catalogue of physical things: a
field for the manufacturer, or for which shelf a locomotive lives on, is
worth writing down and no version of this software will ever read it. What is
required is still required, so a misspelt `model:` is a car that names none
and is refused where the mistake was made.

A car's fields are merged onto its model's here rather than by whatever reads
one, so **the merged result is what is validated** and every consumer sees a
complete car however it was written.

An **entry in a train names either a car or a model**
([ADR-0061](../../../docs/adr/0061-stock-with-nothing-of-its-own-is-named-by-its-model.md)):
`cars` holds identified stock — an item with an address, or with a field
corrected on it — and an item with nothing of its own is named by its model
where it is used. Either way the entry is loaded into a `Car`, so nothing
downstream of the roster reads which shape it was written in.
"""

from collections.abc import Mapping
from typing import Any, cast

from tc49.lib.layout import as_mapping, check_length, check_name, check_required
from tc49.lib.roster import (
    KINDS,
    OFF_ON,
    ORIENTATIONS,
    Car,
    Coupled,
    Function,
    Model,
    Roster,
    Train,
)


def validate_model(doc: Any, name: str) -> Model:
    """One catalogue file: what a product is.

    The file names itself, as a roster does, and the name is the key every
    car refers to it by — so a file whose `model:` disagrees with its path is
    refused rather than filed under one name and referred to by the other.
    """
    where = f"model '{name}'"
    spec = check_required(doc, f"{where} document", {"model", "kind", "length"})
    check_name(spec["model"], "model")
    if spec["model"] != name:
        raise ValueError(f"{where}: file names itself '{spec['model']}'")
    return Model(
        name,
        _kind(spec["kind"], where),
        check_length(spec["length"], where),
        _functions(spec.get("functions"), where),
        _text(spec.get("manufacturer"), f"{where}: manufacturer"),
        _text(spec.get("scale"), f"{where}: scale"),
        _text(spec.get("description"), f"{where}: description"),
    )


def validate_roster(doc: Any, catalogue: Mapping[str, Model]) -> Roster:
    """A railroad's stock: its cars, and the trains made up from them.

    The catalogue is passed in because a car is only complete against it: a
    car names a model, and a model the installation does not have is a car
    nothing can say the length of.
    """
    spec = check_required(doc, "roster document", {"roster", "trains"})
    railroad = spec["roster"]
    check_name(railroad, "roster's railroad")
    where = f"roster '{railroad}'"

    cars: dict[str, Car] = {}
    owner: dict[str, str] = {}  # decoder address -> the car wearing it
    for name, car_spec in as_mapping(spec.get("cars") or {}, f"{where}: cars").items():
        car = _car(car_spec, catalogue, f"{where}: car '{name}'")
        # One railroad, one decoder per address: two cars on one address both
        # answer the same packet, and no run can tell them apart.
        if car.addr is not None:
            if car.addr in owner:
                raise ValueError(
                    f"{where}: cars '{owner[car.addr]}' and '{name}' share"
                    f" address '{car.addr}'"
                )
            owner[car.addr] = name
        cars[name] = car

    trains = {
        name: _train(train_spec, cars, catalogue, f"{where}: train '{name}'")
        for name, train_spec in as_mapping(spec["trains"], f"{where}: trains").items()
    }
    return Roster(railroad, trains, cars)


def _car(doc: Any, catalogue: Mapping[str, Model], where: str) -> Car:
    """A car: its model with fields overridden, merged.

    Zero overrides is the ordinary case and still names a model, so there is
    one shape to read and the model is where a length is corrected once for
    every item of that product.
    """
    spec = check_required(doc, where, {"model"})
    named = spec["model"]
    model = catalogue.get(named) if isinstance(named, str) else None
    if model is None:
        raise ValueError(f"{where}: names unknown model {named!r}")
    return Car(
        model.name,
        _kind(spec["kind"], where) if "kind" in spec else model.kind,
        check_length(spec["length"], where) if "length" in spec else model.length,
        (
            _functions(spec["functions"], where)
            if "functions" in spec
            else model.functions
        ),
        _addr(spec.get("addr"), where),
        # Inherited, never overridden: what a product is stays the product's
        # (`lib.roster.Car`). A car naming these would be describing a
        # different one, so they are not read off the car's own document.
        model.manufacturer,
        model.scale,
        model.description,
    )


def _train(
    doc: Any, cars: Mapping[str, Car], catalogue: Mapping[str, Model], where: str
) -> Train:
    """A train: an ordered list of the stock it is made up of, head first.

    Its length and its kind are derived from those cars and are never
    authored. A train stating `length` and naming no cars is the shape the
    committed rosters had before #223 rewrote them into cars, and it still
    loads for the sake of an older file; stating both would be two ways to
    know one length, which is the field that rots, so it is refused.

    **An empty `cars` list names no cars** and is refused in the same words as
    a train naming neither key: there is no length to derive for such a train
    (`lib.roster.Train.length`), so a roster the store took would be one
    `GET /rosters/<name>/trains` could not answer (#412).

    The catalogue is here because an entry may name a model rather than a car
    (ADR-0061), and a model is what such an entry is built from.
    """
    spec = as_mapping(doc, where)
    if "cars" in spec and "length" in spec:
        raise ValueError(
            f"{where}: states a length and names cars — a train's length is"
            " the sum of its cars and is never authored"
        )
    if "cars" not in spec and "length" not in spec:
        raise ValueError(f"{where}: names no cars")
    priority = spec.get("priority")
    if priority is not None and not isinstance(priority, int):
        raise ValueError(f"{where}: priority must be an integer, got {priority!r}")
    if "length" in spec:
        return Train(
            stated_length=check_length(spec["length"], where), priority=priority
        )

    if not isinstance(spec["cars"], list):
        raise TypeError(f"{where}: cars must be a list, head first")
    if not spec["cars"]:
        raise ValueError(f"{where}: names no cars")
    ordered = [
        _coupled(entry, cars, catalogue, where)
        for entry in cast(list[Any], spec["cars"])
    ]
    return Train(tuple(ordered), priority)


def _coupled(
    entry: Any, cars: Mapping[str, Car], catalogue: Mapping[str, Model], where: str
) -> Coupled:
    """One place in a train: what stands there, and which way round it is
    coupled.

    The entry names **either a car or a model** (ADR-0061). A car is
    identified stock — an item with an address, or with a field corrected on
    that item — and anything else is named by its model here, because ten
    identical hoppers have nothing to tell one from another and a name for
    each would be a distinction the document then asks a person to maintain.
    Naming both would be two ways to say which item this is, so it is refused
    where the mistake was made.

    An entry naming a model builds a car from it with no address and nothing
    overridden: having something of its own to say is exactly what puts an
    item on `cars` instead.
    """
    held = as_mapping(entry, f"{where}: car entry")
    if ("car" in held) == ("model" in held):
        both = "car" in held
        raise ValueError(
            f"{where}: a car entry names either a car or a model, and this"
            f" names {'both' if both else 'neither'}"
        )
    if "car" in held:
        named = held["car"]
        if not isinstance(named, str) or named not in cars:
            raise ValueError(
                f"{where}: names car {named!r}, which the railroad has not"
            )
        car = cars[named]
    else:
        named = held["model"]
        model = catalogue.get(named) if isinstance(named, str) else None
        if model is None:
            raise ValueError(f"{where}: names unknown model {named!r}")
        car = _anonymous(model)
    orientation = held.get("orientation", ORIENTATIONS[0])
    if orientation not in ORIENTATIONS:
        raise ValueError(
            f"{where}: car '{named}' orientation must be"
            f" {' or '.join(repr(one) for one in ORIENTATIONS)},"
            f" got {orientation!r}"
        )
    return Coupled(car, orientation)


def _anonymous(model: Model) -> Car:
    """An item with nothing of its own: its model, entire, with no address.

    A `Car` all the same, so length, kind and functions derive exactly as
    they do for a named one and nothing downstream of the roster can tell the
    two entries apart (ADR-0061).
    """
    return Car(
        model.name,
        model.kind,
        model.length,
        model.functions,
        None,
        model.manufacturer,
        model.scale,
        model.description,
    )


def _kind(kind: Any, where: str) -> str:
    """A model's kind, which is one of four. A train's kind is derived and is
    never written down, so these are the only ones a document says."""
    if kind not in KINDS:
        raise ValueError(
            f"{where}: kind must be {' or '.join(repr(one) for one in KINDS)},"
            f" got {kind!r}"
        )
    return kind


def _text(value: Any, where: str) -> str | None:
    """One of a model's optional descriptive fields, absent where unstated.

    Refused rather than coerced, for `_addr`'s reason one field along: a
    `scale: 160` would read as a number where every other catalogue writes a
    word, and the two would not sort or compare as the same thing.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: must be a non-empty string, got {value!r}")
    return value


def _addr(addr: Any, where: str) -> str | None:
    """A car's decoder address, absent where it has no decoder.

    A string, and not coerced to one: `addr: 460` and `addr: "460"` would
    otherwise be one address written two ways, and two cars wearing them
    would not read as the collision they are.
    """
    if addr is None:
        return None
    if not isinstance(addr, str) or not addr:
        raise ValueError(
            f"{where}: address must be a non-empty string — quote it, as"
            f' `addr: "460"` — got {addr!r}'
        )
    return addr


def _functions(spec: Any, where: str) -> dict[str, Function]:
    """What each function number does on this product.

    The key is the number **written as a string**, because YAML integer keys
    and JSON object keys do not agree, and a value is a string for the same
    reason one level down: YAML reads a bare `off` as a boolean, so the words
    are quoted and a boolean is refused rather than silently renamed.
    """
    functions: dict[str, Function] = {}
    for number, entry in as_mapping(spec or {}, f"{where}: functions").items():
        at = f"{where}: function {number!r}"
        if not isinstance(cast(Any, number), str):
            raise TypeError(f"{at}: the number is written as a string — quote it")
        held = check_required(entry, at, {"name"})
        name = held["name"]
        if not isinstance(name, str) or not name:
            raise ValueError(f"{at}: name must be a non-empty string, got {name!r}")
        functions[number] = Function(name, _values(held.get("values"), at))
    return functions


def _values(spec: Any, where: str) -> tuple[str, ...]:
    """What a function can be in, first entry first: that is what it is in
    when nothing has been commanded. Absent is the plain switch."""
    if spec is None:
        return OFF_ON
    if not isinstance(spec, list) or not spec:
        raise ValueError(f"{where}: values must be a non-empty list, got {spec!r}")
    values: list[str] = []
    for value in cast(list[Any], spec):
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{where}: value must be a non-empty string — quote it, as"
                f' `["off", "on"]` — got {value!r}'
            )
        values.append(value)
    return tuple(values)
