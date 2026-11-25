"""The timetable document: where a railroad's trains start and a list of
entries in time order (#1345, GLOSSARY.md).

The store and the scheduler both read a timetable through this module, as
they read a clock through `tc49.lib.fast_clock`. It has no bus and no file
access: `read_timetable` takes a parsed YAML document and gives a `Timetable`
or a refusal, and `Timetable.document` gives the document back. `read_entry`
and `Entry.document` do the same for one entry.

```yaml
timetable: evening
layout: crossover-yard
start: "06:00"

trains:
  freight_1: { at: yard_w, facing: A-to-B }

entries:
  - { at: "06:02", train: freight_1, to: [dn_e, up_e], dwell: 2, description: meets the express }
  - { at: "06:10", train: freight_1, turn: true }
  - { at: "06:12", train: freight_1, to: [yard_w.B] }
```

The values are frozen. A changed timetable is a new one: `Timetable.added`,
`removed` and `replaced` for its entries, `dataclasses.replace` for its name,
and every one of them holds its entries in order.

A time of day is held in seconds since midnight on a whole minute, which is
what `"HH:MM"` says. `tc49.lib.fast_clock.start_of` rounds a clock's time down
to one.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass, replace
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
    arrival ends, or turn it round. It carries no id, so two entries with the
    same fields are equal. A time that is not a minute of the day is a
    `ValueError`."""

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

    @property
    def turn(self) -> bool:
        """Whether the entry is a turn-round: it has no arrival ends."""
        return not self.to

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
    """A railroad's timetable.

    Made with entries in any order, it holds them in order (see `entries`).
    A `name` or `layout` that is no path segment, or a `start` that is not a
    minute of the day, is a `ValueError`."""

    name: str
    """Its name, a path segment in the store: not empty, with no `/` and no
    leading `.`."""
    layout: str
    """The railroad it belongs to, a path segment as `name` is."""
    start: int
    """The time of day it starts at, in seconds since midnight on a whole
    minute."""
    trains: dict[str, TrainStart]
    """Where each train stands at the start."""
    entries: tuple[Entry, ...]
    """The entries in order of time counted from `start`, so with a start of
    22:00 an entry at 01:00 comes after one at 23:00. Entries in the same
    minute keep the order they were given in."""

    def __post_init__(self) -> None:
        for field, name in (("timetable", self.name), ("layout", self.layout)):
            if not name or "/" in name or name.startswith("."):
                raise ValueError(
                    f"'{field}' is {name!r}: a name is not empty, has no '/'"
                    " and no leading '.'"
                )
        _check_minute(self.start, "a timetable's 'start'")
        # sorted() is stable, so entries in one minute keep the order given.
        ordered = sorted(self.entries, key=lambda entry: self.since_start(entry.at))
        object.__setattr__(self, "entries", tuple(ordered))

    def since_start(self, time: int) -> int:
        """Seconds from `start` to the time of day `time`, in seconds since
        midnight, within the day: `0` to `DAY_S - 1`. With a start of 22:00,
        01:00 is three hours."""
        return (time - self.start) % DAY_S

    def place(self, at: int) -> int:
        """The position in `entries` a new entry at the time of day `at`
        goes in: after the last entry at or before `at`, so after every entry
        that shares its minute."""
        return bisect_right(
            self.entries,
            self.since_start(at),
            key=lambda entry: self.since_start(entry.at),
        )

    def added(self, entry: Entry) -> "Timetable":
        """The timetable with `entry` added at `place(entry.at)`."""
        position = self.place(entry.at)
        return replace(
            self,
            entries=(*self.entries[:position], entry, *self.entries[position:]),
        )

    def removed(self, index: int) -> "Timetable":
        """The timetable without the entry at position `index`."""
        entries = list(self.entries)
        del entries[index]
        return replace(self, entries=tuple(entries))

    def replaced(self, index: int, entry: Entry) -> "Timetable":
        """The timetable with `entry` in place of the one at position
        `index`. Where `entry.at` is the time the old one had, it stays at
        `index`. Where it is another, it moves to its place in the order,
        `self.removed(index).place(entry.at)`."""
        if entry.at != self.entries[index].at:
            return self.removed(index).added(entry)
        entries = list(self.entries)
        entries[index] = entry
        return replace(self, entries=tuple(entries))

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
      empty. One out of order is put in order, not refused.

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

    An entry with a `dwell` of 0 or an empty `description` reads equal to one
    that leaves it out. A block or a train is not checked against a railroad.
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
