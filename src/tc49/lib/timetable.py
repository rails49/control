"""The timetable document: where a railroad's trains start, how long it
runs before it begins again, and a list of entries in time order (#1345,
#1363, GLOSSARY.md).

The store and the scheduler both read a timetable through this module, as
they read a clock through `tc49.lib.fast_clock`. It has no bus and no file
access: `read_timetable` takes a parsed YAML document and gives a `Timetable`
or a refusal, and `Timetable.document` gives the document back. `read_entry`
and `Entry.document` do the same for one entry.

```yaml
timetable: evening
layout: crossover-yard
start: "06:00"
repeat: "1d00:00"

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

A time is held in seconds since midnight of day 0 on a whole minute, and a
length (`repeat`) in seconds on a whole minute. Both are written in the time
form `[<day>d]HH:MM`: `<day>` a whole number without leading zeros, `HH`
`00`–`23` and `MM` `00`–`59`. Leaving out `<day>d` means day 0, so `06:00` and
`0d06:00` are the same time and `1d06:00` is a day later. `read_time` reads
the form and `time_text` writes it, leaving out `0d`.
`tc49.lib.fast_clock.start_of` rounds a clock's time down to a minute.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass, replace
from typing import Any, cast

from tc49.lib.fast_clock import DAY_S
from tc49.lib.layout import FACINGS, as_mapping, check_keys

_HH_MM = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")
_TIME = re.compile(r"(?:(0|[1-9][0-9]*)d)?([01][0-9]|2[0-3]):([0-5][0-9])")
_FIELDS = {"timetable", "layout", "start", "repeat", "trains", "entries"}


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
    same fields are equal. An `at` that is not a whole minute from 0 is a
    `ValueError`."""

    at: int
    """The time it is due, in seconds since midnight of day 0 on a whole
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
        """The entry as the document lists it: `at` in the time form, `to` or
        `turn: true`, `dwell` left out where 0 and `description` left out
        where empty."""
        doc: dict[str, Any] = {"at": time_text(self.at), "train": self.train}
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
    A `name` or `layout` that is no path segment, a `start` that is not a
    minute of day 0, a `repeat` that is not a whole minute greater than 0,
    and an entry outside the repeat are each a `ValueError`."""

    name: str
    """Its name, a path segment in the store: not empty, with no `/` and no
    leading `.`."""
    layout: str
    """The railroad it belongs to, a path segment as `name` is."""
    start: int
    """The time it starts at, on day 0, in seconds since midnight on a whole
    minute."""
    repeat: int
    """The time from `start` to where it begins again, in seconds on a whole
    minute, greater than 0. Every entry's `at` lies from `start` to before
    `start` plus `repeat`."""
    trains: dict[str, TrainStart]
    """Where each train stands at the start."""
    entries: tuple[Entry, ...]
    """The entries in order of `at`, so with a start of 22:00 an entry at
    1d01:00 comes after one at 23:00. Entries in the same minute keep the
    order they were given in."""

    def __post_init__(self) -> None:
        segment(self.name, "'timetable'")
        segment(self.layout, "'layout'")
        _check_minute(self.start, "a timetable's 'start'")
        if self.start >= DAY_S:
            raise ValueError(
                f"a timetable's 'start' is {time_text(self.start)}, not on day 0"
            )
        _check_minute(self.repeat, "a timetable's 'repeat'")
        if not self.repeat:
            raise ValueError("a timetable's 'repeat' is 00:00, not greater than 0")
        last = self.start + self.repeat - 60
        for number, entry in enumerate(self.entries, 1):
            if entry.at < self.start:
                raise ValueError(
                    f"entry {number}: 'at' is {time_text(entry.at)}, before the"
                    f" start {time_text(self.start)}"
                )
            if entry.at > last:
                raise ValueError(
                    f"entry {number}: 'at' is {time_text(entry.at)}, after the last"
                    f" minute {time_text(last)}"
                )
        # sorted() is stable, so entries in one minute keep the order given.
        ordered = sorted(self.entries, key=lambda entry: entry.at)
        object.__setattr__(self, "entries", tuple(ordered))

    def place(self, at: int) -> int:
        """The position in `entries` a new entry at `at` goes in: after the
        last entry at or before `at`, so after every entry that shares its
        minute."""
        return bisect_right(self.entries, at, key=lambda entry: entry.at)

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
            "start": time_text(self.start),
            "repeat": time_text(self.repeat),
            "trains": {
                train: {"at": start.at, "facing": start.facing}
                for train, start in self.trains.items()
            },
            "entries": [entry.document() for entry in self.entries],
        }


def read_timetable(doc: object) -> Timetable:
    """The `Timetable` a parsed timetable document says, or `ValueError` or
    `TypeError` naming the field that is wrong.

    The document has `timetable`, `layout`, `start`, `repeat`, `trains` and
    `entries`, all six and nothing else:

    - `timetable` and `layout` are names (see `Timetable`);
    - `start` is `"HH:MM"` as text, a time on day 0;
    - `repeat` is a length in the time form as text, greater than 0;
    - `trains` maps each train to its `at`, a block, and its `facing`,
      `A-to-B` or `B-to-A`, both and nothing else. It may be empty;
    - `entries` is a list of entries as `read_entry` reads them. It may be
      empty. One out of order is put in order, not refused. One whose `at` is
      before `start`, or at or after `start` plus `repeat`, is refused.

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
    listed = tuple(
        read_entry(one, f"{where}: entry {i + 1}")
        for i, one in enumerate(cast(list[object], entries))
    )
    start = _start(fields["start"], f"{where}: 'start'")
    repeat = read_time(fields["repeat"], f"{where}: 'repeat'")
    try:
        return Timetable(
            fields["timetable"], fields["layout"], start, repeat, trains, listed
        )
    except ValueError as refused:
        raise ValueError(f"{where}: {refused}") from None


def read_entry(doc: object, where: str = "entry") -> Entry:
    """The `Entry` one entry of a timetable document says, or `ValueError` or
    `TypeError` naming the field that is wrong. `where` begins the refusal.

    An entry has `at`, a time in the time form as text, `train`, and one of
    `to` or `turn: true`, not both. `to` is a non-empty list of arrival ends,
    each non-empty text. `dwell` is a whole number of minutes, 0 or more, and goes
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
        read_time(fields["at"], f"{where}: 'at'"),
        _text(fields["train"], f"{where}: 'train'"),
        to,
        dwell,
        description,
    )


def segment(name: str, what: str) -> str:
    """`name` where it is one path segment in the store, as a timetable's
    name and its railroad's are: not empty, with no `/` and no leading `.`.
    Any other is a `ValueError` saying `what` it is."""
    if not name or "/" in name or name.startswith("."):
        raise ValueError(
            f"{what} is {name!r}: a name is not empty, has no '/' and no leading '.'"
        )
    return name


def read_time(value: object, what: str) -> int:
    """A time or a length in the time form `[<day>d]HH:MM`, as text, in
    seconds: `1d06:00` is 108000. Anything else is a `ValueError` that begins
    with `what`."""
    matched = _TIME.fullmatch(value) if isinstance(value, str) else None
    if matched is None:
        raise ValueError(f'{what} is {value!r}, not "[<day>d]HH:MM" quoted')
    day = int(matched[1] or 0)
    return day * DAY_S + (int(matched[2]) * 60 + int(matched[3])) * 60


def time_text(time: int) -> str:
    """A time or a length in seconds on a whole minute, 0 or more, in the
    time form: `HH:MM` on day 0 and `<day>dHH:MM` on any other."""
    day, within = divmod(time // 60, DAY_S // 60)
    hh_mm = f"{within // 60:02d}:{within % 60:02d}"
    return f"{day}d{hh_mm}" if day else hh_mm


def _check_minute(time: int, what: str) -> None:
    if time < 0 or time % 60:
        raise ValueError(f"{what} of {time} s is not a whole minute from 0")


def _text(value: object, what: str) -> str:
    """`value` where it is text and not empty."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{what} is {value!r}, not non-empty text")
    return value


def _start(value: object, what: str) -> int:
    """`"HH:MM"`, a time on day 0, as seconds since midnight."""
    matched = _HH_MM.fullmatch(value) if isinstance(value, str) else None
    if matched is None:
        raise ValueError(f'{what} is {value!r}, not "HH:MM" quoted')
    return (int(matched[1]) * 60 + int(matched[2])) * 60
