"""The timetable document: where a railroad's trains start and a list of
entries in time order (#1345, GLOSSARY.md).

The store and the scheduler both read a timetable through this module, as
they read a clock through `tc49.lib.fast_clock`. It has no bus and no file
access: `read_timetable` takes a parsed YAML document and gives a `Timetable`
or a refusal, and `Timetable.document` gives the document back.
"""

import re
from dataclasses import dataclass
from typing import Any, cast

from tc49.lib.fast_clock import DAY_S
from tc49.lib.layout import FACINGS, as_mapping, check_keys

_HH_MM = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")
_FIELDS = {"timetable", "layout", "start", "trains", "entries"}


@dataclass(frozen=True)
class TrainStart:
    """Where a train stands when its timetable starts."""

    at: str
    """The block."""
    facing: str
    """`A-to-B` or `B-to-A`, one of `tc49.lib.layout.FACINGS`."""


@dataclass(frozen=True)
class Entry:
    """One row of a timetable: at a time, send a train to one of a set of
    arrival ends, or turn it round."""

    at: int
    """The time of day it is due, in seconds since midnight on a whole
    minute."""
    train: str
    to: tuple[str, ...] = ()
    """The arrival ends, each `<block>.<end>` or a bare `<block>` meaning
    either end. Empty on a turn-round."""
    dwell: int = 0
    """The least whole fast-clock minutes the train stands where the entry
    took it."""
    description: str = ""
    """A person's note, empty where there is none."""

    def __post_init__(self) -> None:
        _check_minute(self.at, "an entry's 'at'")

    def document(self) -> dict[str, Any]:
        """The entry as the document lists it: `at` as `"HH:MM"`, `to` or
        `turn: true`, `dwell` left out where 0 and `description` left out
        where empty."""
        doc: dict[str, Any] = {"at": _hh_mm(self.at), "train": self.train}
        if self.to:
            doc["to"] = list(self.to)
        else:
            doc["turn"] = True
        if self.dwell:
            doc["dwell"] = self.dwell
        if self.description:
            doc["description"] = self.description
        return doc


@dataclass(frozen=True)
class Timetable:
    """A railroad's timetable."""

    name: str
    layout: str
    """The railroad it belongs to."""
    start: int
    """The time of day it starts at, in seconds since midnight on a whole
    minute."""
    trains: dict[str, TrainStart]
    """Where each train stands at the start."""
    entries: tuple[Entry, ...]

    def __post_init__(self) -> None:
        for field, name in (("timetable", self.name), ("layout", self.layout)):
            if not name or "/" in name or name.startswith("."):
                raise ValueError(
                    f"'{field}' is {name!r}: a name is not empty, has no '/'"
                    " and no leading '.'"
                )
        _check_minute(self.start, "a timetable's 'start'")

    def document(self) -> dict[str, Any]:
        """The store's document. `read_timetable` reads it as an equal
        value."""
        return {
            "timetable": self.name,
            "layout": self.layout,
            "start": _hh_mm(self.start),
            "trains": {
                train: {"at": start.at, "facing": start.facing}
                for train, start in self.trains.items()
            },
            "entries": [entry.document() for entry in self.entries],
        }


def read_timetable(doc: object) -> Timetable:
    """The `Timetable` a parsed timetable document says, or `ValueError` or
    `TypeError` naming the field that is wrong.

    The document has `timetable`, `layout`, `start`, `trains` and `entries`,
    all five and nothing else:

    - `timetable` and `layout` are names (see `Timetable`);
    - `start` is `"HH:MM"` as text;
    - `trains` maps each train to its `at`, a block, and its `facing`,
      `A-to-B` or `B-to-A`, both and nothing else. It may be empty;
    - `entries` is a list of entries as `read_entry` reads them. It may be
      empty, and need not be in order.

    A time is text because YAML 1.1, which the store reads in, takes an
    unquoted `12:30` as the integer 750. Only the shape is checked: the
    module is given no layout and no roster, so a block or a train no
    railroad has is read.
    """
    check_keys(doc, "timetable document", _FIELDS)
    fields = cast(dict[str, Any], doc)
    for field in ("timetable", "layout"):
        if not isinstance(fields[field], str):
            raise TypeError(
                f"timetable document: '{field}' is {fields[field]!r}, not text"
            )
    where = f"timetable {fields['timetable']!r}"

    trains: dict[str, TrainStart] = {}
    listed = cast(dict[object, Any], as_mapping(fields["trains"], f"{where}: 'trains'"))
    for name, start in listed.items():
        train = _text(name, f"{where}: a train in 'trains'")
        here = f"{where}: train {train!r}"
        check_keys(start, here, {"at", "facing"})
        facing = start["facing"]
        if facing not in FACINGS:
            raise ValueError(
                f"{here}: 'facing' is {facing!r}, not"
                f" {' or '.join(repr(one) for one in FACINGS)}"
            )
        trains[train] = TrainStart(_text(start["at"], f"{here}: 'at'"), facing)

    entries = fields["entries"]
    if not isinstance(entries, list):
        raise TypeError(
            f"{where}: 'entries' must be a list, got {type(entries).__name__}"
        )
    return Timetable(
        fields["timetable"],
        fields["layout"],
        _time(fields["start"], f"{where}: 'start'"),
        trains,
        tuple(
            read_entry(one, f"{where}: entry {i + 1}")
            for i, one in enumerate(cast(list[object], entries))
        ),
    )


def read_entry(doc: object, where: str = "entry") -> Entry:
    """The `Entry` one entry of a timetable document says, or `ValueError` or
    `TypeError` naming the field that is wrong. `where` begins the refusal.

    An entry has `at`, `"HH:MM"` as text, `train`, and one of `to` or
    `turn: true`, not both. `to` is a non-empty list of arrival ends, each
    non-empty text. `dwell` is a whole number of minutes, 0 or more, and goes
    only with `to`. A bool is no number. `description` is text. `dwell` and
    `description` may be left out, and any other key is refused.
    """
    check_keys(doc, where, {"at", "train"}, {"to", "turn", "dwell", "description"})
    fields = cast(dict[str, Any], doc)
    if ("to" in fields) == ("turn" in fields):
        raise ValueError(f"{where}: has one of 'to' or 'turn', not both or neither")
    to: tuple[str, ...] = ()
    dwell = 0
    if "turn" in fields:
        if fields["turn"] is not True:
            raise ValueError(f"{where}: 'turn' is {fields['turn']!r}, not true")
        if "dwell" in fields:
            raise ValueError(f"{where}: 'dwell' goes only with 'to'")
    else:
        ends = fields["to"]
        if not isinstance(ends, list) or not ends:
            raise ValueError(
                f"{where}: 'to' is {ends!r}, not a non-empty list of arrival ends"
            )
        to = tuple(
            _text(end, f"{where}: an arrival end in 'to'")
            for end in cast(list[object], ends)
        )
        dwell = fields.get("dwell", 0)
        if isinstance(dwell, bool) or not isinstance(dwell, int) or dwell < 0:
            raise ValueError(
                f"{where}: 'dwell' is {dwell!r}, not a whole number of minutes,"
                " 0 or more"
            )
    description = fields.get("description", "")
    if not isinstance(description, str):
        raise TypeError(f"{where}: 'description' is {description!r}, not text")
    return Entry(
        _time(fields["at"], f"{where}: 'at'"),
        _text(fields["train"], f"{where}: 'train'"),
        to,
        dwell,
        description,
    )


def _check_minute(time: int, what: str) -> None:
    if not 0 <= time < DAY_S or time % 60:
        raise ValueError(f"{what} of {time} s is not a minute of the day")


def _text(value: object, what: str) -> str:
    """`value` where it is text and not empty."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{what} is {value!r}, not non-empty text")
    return value


def _time(value: object, what: str) -> int:
    """`"HH:MM"` as seconds since midnight."""
    matched = _HH_MM.fullmatch(value) if isinstance(value, str) else None
    if matched is None:
        raise ValueError(f'{what} is {value!r}, not "HH:MM" quoted')
    return (int(matched[1]) * 60 + int(matched[2])) * 60


def _hh_mm(time: int) -> str:
    """Seconds since midnight on a whole minute as `"HH:MM"`."""
    minutes = time // 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
