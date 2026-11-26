"""The timetable's release rule: the state of the loaded timetable, and what
happens next (#1345, #1351, #1363).

It has no bus, no store and no clock of its own, and imports `tc49.lib` only.
The scheduler tells it what the bus said and asks it what to do.

`State` is a value. It holds what the scheduler was told of the railroad, and
the loaded timetable where there is one: its phase, Record, how far it has
run, the requests to start blocks not yet ended, and each entry's `Progress`.
Every function that is told something takes a state and returns a new one. A
state with no timetable loaded takes them all, and keeps what it was told for
the timetable loaded next.

| The scheduler reads or does | It calls |
|---|---|
| a `tc49/layout/state/clock` row | `clocked(state, time, speed_up)` |
| `tc49/layout/state/power` | `powered(state, reads)` |
| the trains on the layout | `placed(state, trains)` |
| `request_submitted`, whoever wrote it | `announced(state, request, train)` |
| `request_completed`, `_rejected`, `_cancelled` | `ended(state, request, how)` |
| it submitted the request for an entry `due` listed | `released(state, index, request)` |
| it applied the turn-round of an entry `due` listed | `turned(state, index)` |
| it published `clock_wanted` because `starts` said so | `started(state)` |
| it composed and submitted a `request_wanted` gesture | `dragged(state, train, to, request)` |
| it applied a `reversal_wanted` gesture | `turned_round(state, train)` |
| `timetable_record_wanted` | `recording(state, record)` |
| `entry_wanted` | `changed(state, was, now)` |
| `timetable_rename_wanted`, where the store has none of that name | `renamed(state, to)` |
| `timetable_repeat_wanted` | `repeated(state, repeat)` |
| it makes a new timetable because `untitled` or `new` said so | `made(state, name, layout, trains)` |
| it read a timetable from the store because `loads` said so | `loaded(state, timetable)` |
| it submitted a request to a start block | `positioned(state, request)` |
| a retained state row, at a restart | `restarted(said, document)` |
| the first allocation row after a restart | `listed(state, requests)` |

A request the scheduler submits for an entry it tells with `released`, and
one for a gesture with `dragged`. Each `request_submitted` also comes back
off the bus and is told with `announced`, which then changes nothing.

After each of them it asks, in this order:

- `untitled(state)`: whether to make the timetable named `untitled`. On
  `timetable_wanted` with `new` it asks `new(state)`. Where the answer is yes
  it calls `made` and publishes `tc49/layout/clock_wanted` with
  `state.clock`. On `timetable_wanted` without `new` it asks `loads(state)`
  and calls `loaded`.
- `starts(state)`: whether to start. On a person's gesture it asks
  `starts(state, asked=True)`. Where the answer is yes it publishes
  `tc49/layout/clock_wanted` with `state.timetable.start` and calls `started`.
- `due(state)`: the entries to release now, in order, at most one for a train.
  It composes each one with `to` as a drag of `entry.train` to `entry.to` and
  calls `released` with the id, or applies the turn-round and calls `turned`.
  One it could not do it leaves untold, and `due` lists it again. After a
  `turned` the train's next entry can be due at once, so it asks again.
- `row(state)`: the payload of `tc49/schedule/state/timetable`, less its
  stamp, which it publishes where it differs from the last one.

A position `due` gives is good until the timetable's entries change.

The rules, in the words of #1345 and #1363:

- **New.** A new timetable takes the clock's time of day, rounded down to
  the minute, as `start`, and repeats every day. It has no entries, Record is
  on and it is `running` at once. The scheduler makes `untitled` when power
  reads `on` and no timetable is loaded (`untitled`). A person asks for one
  by name, which is dropped unless power reads `off` (`new`). Both wait for a
  clock row and for the trains on the layout.
- **Record.** While the timetable is `running` and Record is on, a drag at
  clock time c adds an entry at `start` plus ((c − `start`) mod `repeat`),
  rounded down to the minute, `out` as the request the drag made in round
  ⌊(c − `start`) / `repeat`⌋, and a turn-round adds an entry that has
  `ended` in that round. A new entry goes after the last entry at or
  before its time. In any other phase, or with Record off, a drag is a
  request with no entry (`dragged`, `turned_round`).
- **Edit.** A person changes or deletes an entry by naming it as it reads
  now: the first entry equal to it, and none where no entry is. A change to
  an `at` outside the repeat is dropped. A changed `at` moves the entry to
  its place in the order. The entry keeps its round, its state, its
  request and its ending, and a request that has gone out is left alone.
  It is taken in every phase and with Record on or off (`changed`).
- **Repeat.** A person sets the loaded timetable's `repeat` while power
  reads `off`, in `loaded` and `running`. It is dropped where an entry would
  fall at or after `start` plus `repeat`. Entries keep their rounds
  (`repeated`).
- **Load.** A timetable a person asks for by name is loaded only while power
  reads `off`, and once the trains on the layout were told (`loads`). Its
  phase is `loaded` and Record is off. The requests the scheduler submits to
  send trains to their start blocks are listed until each ends (`loaded`,
  `positioned`).
- **Start.** A `loaded` timetable starts when every request to a start block
  has ended, however it ended, and power reads `on`. It also starts when a
  person asks. A timetable with no such request starts when power reads `on`
  (`starts`).
- **Time.** The clock row's time is the clock's: seconds since midnight of
  day 0, with no upper limit (`clocked`). An entry's `at` is on the same
  scale. Starting a timetable sets the clock to `start` on day 0, and
  making one sets it to its time of day on day 0.
- **Start handshake.** After the scheduler sets the clock to the start,
  clock rows are ignored until one reads from the start to two beats past
  it (`clocked`).
- **Round.** A timetable repeats every `repeat` and never ends. Round n of
  an entry is due at its `at` plus n × `repeat`. Each entry's `Progress`
  holds its round, from 0.
- **Due.** An entry is due when the clock has reached its due time in its
  round. It is `later` until it is due and `held` while it is due and
  waits on its train. A clock set forward makes the entries passed over
  due, in order, and a clock set back makes the entries not yet out
  `later` again.
- **Next round.** An entry whose state is final (`ended`, `rejected`,
  `cancelled`, `skipped`) moves to the next round, `later`, once the clock
  reaches the start of that round, `start` plus (n + 1) × `repeat`. An
  entry that is not final stays in its round until it is final, and moves
  at once if the next round has already begun. A train still late when
  the next round begins runs late into it, and nothing is dropped. Nothing
  moves back a round, so nothing goes out twice.
- **Order.** A train's entries are released in order, round after round:
  an entry waits for every entry of its train that comes before it in
  (round, position) order, so a train's first entry in round n + 1 waits
  for its last entry of round n. It is released when it is due, those
  entries have ended, been rejected, been cancelled or been skipped, and,
  where the train's entry before it ended by arrival, its dwell has passed
  since the arrival.
- **Dwell.** `Progress.ended` is the clock's time at the arrival, so a
  dwell runs on the clock, across midnight too.
- **Turn-round.** A turn-round also waits while the train has any request in
  flight. An entry with `to` does not wait for a person's request.
- **Skipped.** A train off the layout when its entry would be released has
  that entry `skipped` in that round only. It runs again in the next round
  once the train is placed, and the train's later entries run if it is
  placed later.
- **No retry.** A rejected or cancelled entry is not released again in its
  round. No entry is skipped for being late.
- **Restart.** The first clock row gives the time. Each entry's round and
  state come from the retained row (`restarted`).

`State` applies Next round, Due, Order and Skipped when it is made. So every state
holds them, and a function here only makes the new state, with `replace` or
whole.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, cast

from tc49.lib.fast_clock import DAY_S, start_of
from tc49.lib.inventory import OFF, ON
from tc49.lib.timetable import (
    Entry,
    Timetable,
    TrainStart,
    read_entry,
    read_timetable,
)

UNTITLED = "untitled"
"""The name of the timetable the scheduler makes itself."""

LOADED = "loaded"
RUNNING = "running"
PHASES = (LOADED, RUNNING)
"""The phases of a loaded timetable."""

LATER = "later"
HELD = "held"
OUT = "out"
ENDED = "ended"
REJECTED = "rejected"
CANCELLED = "cancelled"
SKIPPED = "skipped"
STATES = (LATER, HELD, OUT, ENDED, REJECTED, CANCELLED, SKIPPED)
"""The states of an entry."""
FINAL = (ENDED, REJECTED, CANCELLED, SKIPPED)
"""The states an entry moves to its next round from."""

COMPLETED = "completed"
_ENDINGS = {COMPLETED: ENDED, REJECTED: REJECTED, CANCELLED: CANCELLED}


@dataclass(frozen=True)
class Progress:
    """How far one entry has got."""

    state: str = LATER
    """One of `STATES`: `later` (its time has not come), `held` (due, waiting
    on the train), `out`, `ended`, `rejected`, `cancelled` or `skipped`."""
    request: str | None = None
    """The id of the request it went out as. None on a turn-round and on an
    entry that has not gone out."""
    ended: int | None = None
    """The clock's time at the arrival, where it ended by arrival, in seconds
    since midnight of day 0. None where it ended any other way. It is kept
    when the entry moves to its next round, until it goes out again, so the
    dwell holds back the train's next entry."""
    round: int = 0
    """The round its `state` is for, from 0. In round n it is due at its `at`
    plus n × `repeat`."""


@dataclass(frozen=True)
class Release:
    """An entry to release now: `entry.to` to compose as a drag of
    `entry.train`, or a turn-round where `entry.turn`."""

    index: int
    """Its position in the timetable's entries, which `released` and `turned`
    take."""
    entry: Entry


@dataclass(frozen=True)
class State:
    """What the release rule holds. `State()` has no timetable loaded.

    A state made with a timetable holds the rule: each entry in a final
    state whose next round has begun is in that round, each entry not yet
    out is `later` or `held` as the clock says, and one that would be
    released for a train off the layout is `skipped`. Made with no
    `progress`, every entry is `later` in round 0 before that.
    A `progress` that is not one for each entry is a `ValueError`."""

    timetable: Timetable | None = None
    """The loaded timetable, or None. The fields down to `progress` mean
    nothing without one."""
    phase: str = LOADED
    """`loaded` or `running`."""
    record: bool = False
    """Whether a person's drags and turn-rounds are added as entries."""
    starting: bool = False
    """Whether the timetable was started and no clock row has read its start
    time since."""
    positioning: tuple[str, ...] = ()
    """The ids of the requests to start blocks not yet ended."""
    progress: tuple[Progress, ...] = ()
    """One for each entry of `timetable.entries`, in their order."""
    clock: int | None = None
    """The clock's time, in seconds since midnight of day 0: what the last
    clock row read, or the time the scheduler set. None where none was told,
    as after a restart until the first clock row, and nothing is due until
    then."""
    power: str = OFF
    """What `tc49/layout/state/power` last read."""
    placed: frozenset[str] | None = None
    """The trains on the layout. None until they were told, and nothing is
    released or skipped until then."""
    in_flight: Mapping[str, str] = field(default_factory=dict[str, str])
    """Request id to its train, for each request announced and not ended."""

    def __post_init__(self) -> None:
        if self.timetable is None:
            return
        entries = len(self.timetable.entries)
        progress = self.progress or (Progress(),) * entries
        if len(progress) != entries:
            raise ValueError(f"progress is {len(progress)} for {entries} entries")
        object.__setattr__(self, "progress", _ruled(self, progress)[0])


def clocked(state: State, time: int, speed_up: float) -> State:
    """The state after a clock row: `time` and `speed_up` as
    `tc49/layout/state/clock` says them.

    The row's time is the clock's. So a clock set forward makes the entries
    passed over due, in order, and a clock set back makes the entries not
    yet out wait again. An entry that went out is not released again.

    After a start (`started`) a row said before the clock was set may still
    arrive. Rows are ignored until one reads from `start` to two beats past
    it, 2 × `speed_up` seconds.
    """
    timetable = state.timetable
    if state.starting and timetable is not None:
        if not timetable.start <= time <= timetable.start + 2 * speed_up:
            return state
        return replace(state, clock=time, starting=False)
    return replace(state, clock=time)


def powered(state: State, reads: str) -> State:
    """The state after `tc49/layout/state/power` read `reads`."""
    return replace(state, power=reads)


def placed(state: State, trains: frozenset[str]) -> State:
    """The state with `trains` the trains on the layout, all of them."""
    return replace(state, placed=trains)


def announced(state: State, request: str, train: str) -> State:
    """The state after a request with the id `request` was announced for
    `train`, whoever submitted it."""
    return replace(state, in_flight={**state.in_flight, request: train})


def ended(state: State, request: str, how: str) -> State:
    """The state after the request with the id `request` ended: `how` is
    `completed`, `rejected` or `cancelled`.

    The entry that went out as it is `ended` at the clock's time, `rejected`
    or `cancelled`, in its round, and is not released again in that round. A request to a
    start block is no longer listed in `positioning`.
    """
    progress = tuple(
        (
            replace(
                one,
                state=_ENDINGS[how],
                ended=state.clock if how == COMPLETED else None,
            )
            if one.state == OUT and one.request == request
            else one
        )
        for one in state.progress
    )
    return replace(
        state,
        progress=progress,
        positioning=tuple(one for one in state.positioning if one != request),
        in_flight={
            one: train for one, train in state.in_flight.items() if one != request
        },
    )


def released(state: State, index: int, request: str) -> State:
    """The state after the scheduler submitted the entry at position `index`
    as the request with the id `request`: the entry is `out` in its round,
    and the request is in flight for its train."""
    assert state.timetable is not None
    train = state.timetable.entries[index].train
    out = Progress(OUT, request, round=state.progress[index].round)
    return replace(
        state,
        progress=_with(state.progress, index, out),
        in_flight={**state.in_flight, request: train},
    )


def turned(state: State, index: int) -> State:
    """The state after the scheduler applied the turn-round at position
    `index`: the entry is `ended` in its round."""
    done = Progress(ENDED, round=state.progress[index].round)
    return replace(state, progress=_with(state.progress, index, done))


def untitled(state: State) -> bool:
    """Whether to make the timetable named `untitled`, which the scheduler
    does with `made`: power reads `on`, no timetable is loaded, a clock row
    was told and the trains on the layout were told."""
    return state.timetable is None and state.power == ON and _makes(state)


def new(state: State) -> bool:
    """Whether a new timetable a person asks for by name is made: power reads
    `off`, a clock row was told and the trains on the layout were told. It
    replaces the timetable loaded."""
    return state.power == OFF and _makes(state)


def _makes(state: State) -> bool:
    """Whether the state has what a new timetable takes: the clock's time
    for its start, and the trains told for where they stand."""
    return state.clock is not None and state.placed is not None


def made(
    state: State, name: str, layout: str, trains: Mapping[str, TrainStart]
) -> State:
    """The state with a new timetable named `name` loaded, for the railroad
    `layout`, in place of the one loaded. The scheduler calls it where
    `untitled` or `new` said yes.

    Its `start` is the clock's time of day rounded down to the minute, its
    `repeat` one day, and `trains` is where each train on the layout stands.
    It has no entries, Record is on and it is `running` at once. The clock
    is set to its time of day on day 0, to the second, which the scheduler
    asks for on `tc49/layout/clock_wanted` with `clock`. What the state was
    told of the railroad is kept.

    A `name` or `layout` the document does not take is a `ValueError`
    (`tc49.lib.timetable.Timetable`).
    """
    assert state.clock is not None
    clock = state.clock % DAY_S
    return State(
        Timetable(name, layout, start_of(clock), DAY_S, dict(trains), ()),
        RUNNING,
        True,
        clock=clock,
        power=state.power,
        placed=state.placed,
        in_flight=state.in_flight,
    )


def recording(state: State, record: bool) -> State:
    """The state with Record on or off, as a person asked. With no timetable
    loaded there is none to switch, and the state is as it was."""
    if state.timetable is None:
        return state
    return replace(state, record=record)


def dragged(state: State, train: str, to: tuple[str, ...], request: str) -> State:
    """The state after the scheduler composed a `request_wanted` gesture for
    `train` to the arrival ends `to`, as the gesture gave them, and submitted
    it as the request with the id `request`. The request is in flight for
    the train.

    While the timetable is `running` and Record is on, the drag is added as
    an entry: `at` the time `_now` gives, after the last entry at or before
    that time, `out` as `request` in the round `_round` gives. In any other phase, with Record off, with
    no timetable loaded, and after a restart until the first clock
    row, it is a request with no entry. So is a drag to no arrival end: an
    entry with none is a turn-round.
    """
    flying = {**state.in_flight, request: train}
    if not to or not _records(state):
        return replace(state, in_flight=flying)
    entry = Entry(_now(state), train, to)
    out = Progress(OUT, request, round=_round(state))
    return _added(replace(state, in_flight=flying), entry, out)


def turned_round(state: State, train: str) -> State:
    """The state after the scheduler applied a `reversal_wanted` gesture for
    `train`. Where `dragged` adds an entry, this adds one with `turn`, which
    has `ended` in the round `_round` gives. A turn-round the scheduler
    dropped is not told."""
    if not _records(state):
        return state
    done = Progress(ENDED, round=_round(state))
    return _added(state, Entry(_now(state), train), done)


def _records(state: State) -> bool:
    """Whether a person's drag or turn-round is added as an entry now."""
    return (
        state.timetable is not None
        and state.phase == RUNNING
        and state.record
        and state.clock is not None
    )


def _now(state: State) -> int:
    """The `at` a drag or a turn-round is recorded at: `start` plus the
    clock's time since `start` within the repeat, rounded down to the
    minute. With a start of 23:58, the clock at 00:01 gives 1d00:01."""
    timetable = state.timetable
    assert timetable is not None and state.clock is not None
    within = (state.clock - timetable.start) % timetable.repeat
    return timetable.start + within - within % 60


def _round(state: State) -> int:
    """The round a drag or a turn-round is recorded in: the whole repeats
    from `start` to the clock, and 0 with the clock before `start`."""
    timetable = state.timetable
    assert timetable is not None and state.clock is not None
    return max(0, (state.clock - timetable.start) // timetable.repeat)


def _added(state: State, entry: Entry, progress: Progress) -> State:
    """`state` with `entry` added to its timetable, and `progress` at the
    position the entry took."""
    timetable = state.timetable
    assert timetable is not None
    position = timetable.place(entry.at)
    return replace(
        state,
        timetable=timetable.added(entry),
        progress=(
            *state.progress[:position],
            progress,
            *state.progress[position:],
        ),
    )


def changed(state: State, was: Entry, now: Entry | None) -> State:
    """The state after a person changed the entry equal to `was` to `now`,
    or deleted it where `now` is None.

    The entry is the first one equal to `was` in every field of the
    document, a `dwell` left out being 0. Where none is, and with no
    timetable loaded, the state is as it was. So it is where `now` is before
    `start`, or at or after `start` plus `repeat`. It is taken in every phase
    and with Record on or off.

    A changed `at` moves the entry to its place in the order, after the last
    entry at or before its new time. The entry keeps its state, its request
    and its ending, and so does one that has gone out: its request is left
    alone, changed or deleted. It keeps its round. An entry not yet out is
    `later` or `held` as its new time says, and is due at that time in its
    round.
    """
    timetable = state.timetable
    if timetable is None or was not in timetable.entries:
        return state
    if now is not None and not (
        timetable.start <= now.at < timetable.start + timetable.repeat
    ):
        return state
    index = timetable.entries.index(was)
    rest = timetable.removed(index)
    progress = [*state.progress[:index], *state.progress[index + 1 :]]
    if now is None:
        return replace(state, timetable=rest, progress=tuple(progress))
    position = index if now.at == was.at else rest.place(now.at)
    progress.insert(position, state.progress[index])
    return replace(
        state, timetable=timetable.replaced(index, now), progress=tuple(progress)
    )


def renamed(state: State, to: str) -> State:
    """The state with the loaded timetable named `to`, and nothing else
    changed. With no timetable loaded the state is as it was. A `to` the
    document does not take is a `ValueError`
    (`tc49.lib.timetable.Timetable`). Whether the store has a timetable of
    that name is the scheduler's to ask."""
    if state.timetable is None:
        return state
    return replace(state, timetable=replace(state.timetable, name=to))


def repeated(state: State, repeat: int) -> State:
    """The state with the loaded timetable repeating every `repeat` seconds,
    greater than 0, and each entry in the round it was in. The state is as
    it was unless power reads `off` and a timetable is loaded, and where an
    entry would fall at or after `start` plus `repeat`."""
    if state.timetable is None or state.power != OFF:
        return state
    try:
        timetable = replace(state.timetable, repeat=repeat)
    except ValueError:  # an entry outside the repeat
        return state
    return replace(state, timetable=timetable)


def listed(state: State, requests: Mapping[str, str]) -> State:
    """The state after the first `tc49/dispatch/state/allocation` row a
    restart reads: `requests` is each request the row lists, its id to its
    train. They are the requests in flight.

    A request can end while the scheduler is down. An entry that is `out`
    whose request the row does not list is `ended`, with no time of arrival
    and so no dwell. A request to a start block the row does not list is no
    longer listed in `positioning`.
    """
    progress = tuple(
        (
            replace(one, state=ENDED, ended=None)
            if one.state == OUT and one.request not in requests
            else one
        )
        for one in state.progress
    )
    return replace(
        state,
        progress=progress,
        positioning=tuple(one for one in state.positioning if one in requests),
        in_flight=dict(requests),
    )


def loads(state: State) -> bool:
    """Whether a timetable a person asks for by name is loaded, which the
    scheduler does with `loaded`: power reads `off` and the trains on the
    layout were told."""
    return state.power == OFF and state.placed is not None


def loaded(state: State, timetable: Timetable) -> State:
    """The state with `timetable`, read from the store, loaded in place of
    the one loaded. The scheduler calls it where `loads` said yes.

    Its phase is `loaded` and Record is off. No entry has gone out and no
    request to a start block is listed. What the state was told of the
    railroad is kept, the requests in flight among them.
    """
    return State(
        timetable,
        clock=state.clock,
        power=state.power,
        placed=state.placed,
        in_flight=state.in_flight,
    )


def positioned(state: State, request: str) -> State:
    """The state after the scheduler submitted the request with the id
    `request` to send a train to its start block: it is listed in
    `positioning` until it ends."""
    return replace(state, positioning=(*state.positioning, request))


def starts(state: State, asked: bool = False) -> bool:
    """Whether to start the timetable, which the scheduler does by asking for
    the clock to be set to `start` and calling `started`.

    A `loaded` timetable starts when every request to a start block has
    ended, however it ended, and power reads `on`. It also starts when a
    person asks, which `asked` says. A timetable with no such request starts
    when power reads `on`. In any other phase, and with no timetable loaded,
    the answer is no.
    """
    return (
        state.timetable is not None
        and state.phase == LOADED
        and (asked or (not state.positioning and state.power == ON))
    )


def started(state: State) -> State:
    """The state after the scheduler asked for the clock to be set to the
    timetable's start time: `running`, the clock at `start` on day 0, with
    clock rows ignored until one reads it (`clocked`)."""
    assert state.timetable is not None
    return replace(state, phase=RUNNING, clock=state.timetable.start, starting=True)


def due(state: State) -> tuple[Release, ...]:
    """The entries to release now, in order of round and then position.

    An entry is due when the clock has reached its `at` plus its round ×
    `repeat`. A train's entries are released in order, round after round:
    an entry is released when it is due, every entry of its train before it
    in that order has ended, been rejected, been cancelled or been skipped,
    and, where the train's entry before it ended by arrival, its dwell has
    passed since the arrival. The entry before a train's first is its last,
    in the round before. A turn-round also waits
    while the train has any request in flight. An entry with `to` does not
    wait for a person's request.

    So at most one entry is listed for a train, and none for a train off the
    layout, whose entry is `skipped` instead. None is listed unless the
    timetable is `running`, and none before the trains on the layout were
    told.
    """
    timetable = state.timetable
    if timetable is None:
        return ()
    return tuple(
        Release(index, timetable.entries[index])
        for index in _ruled(state, state.progress)[1]
    )


def row(state: State) -> dict[str, Any]:
    """The payload of `tc49/schedule/state/timetable`, less its stamp.

    `timetable` is the loaded timetable's name, or None, in which case no
    other field is present. Otherwise `phase`, `record`, `start` as
    `"HH:MM"`, `repeat`, `trains` as the document has them, `positioning` and
    `entries`: each entry's document fields, its `state`, its `round`,
    `request` where it went out as a request and `ended` where it ended by
    arrival. `repeat` and each entry's `at` are in the time form
    (`tc49.lib.timetable`).
    """
    if state.timetable is None:
        return {"timetable": None}
    document = state.timetable.document()
    entries: list[dict[str, Any]] = []
    for entry, progress in zip(document["entries"], state.progress):
        entry["state"] = progress.state
        entry["round"] = progress.round
        if progress.request is not None:
            entry["request"] = progress.request
        if progress.ended is not None:
            entry["ended"] = progress.ended
        entries.append(entry)
    return {
        "timetable": document["timetable"],
        "phase": state.phase,
        "record": state.record,
        "start": document["start"],
        "repeat": document["repeat"],
        "trains": document["trains"],
        "positioning": list(state.positioning),
        "entries": entries,
    }


def restarted(said: object, document: Timetable) -> State | None:
    """The state a restart takes from `said`, a retained
    `tc49/schedule/state/timetable` value, and `document`, the timetable the
    store has under the name it gives. None where the row cannot be read or
    names another timetable.

    The phase, Record, `positioning` and each entry's state, round, request
    and ending are the row's. So are the start time, the repeat, the trains
    and the entries where the document's differ. The document gives the
    railroad's name.

    The state has been told nothing of the railroad. Its clock is None, and
    the first clock row gives it (`clocked`).
    """
    try:
        return _read(said, document)
    except (KeyError, TypeError, ValueError):
        return None


def _read(said: object, document: Timetable) -> State:
    """`restarted`, with a `KeyError`, `TypeError` or `ValueError` where the
    row cannot be read."""
    if not isinstance(said, dict):
        raise TypeError("the row is no mapping")
    fields = cast(dict[str, Any], said)
    if fields["timetable"] != document.name:
        raise ValueError("the row names another timetable")
    timetable = read_timetable(
        {
            "timetable": document.name,
            "layout": document.layout,
            "start": fields["start"],
            "repeat": fields["repeat"],
            "trains": fields["trains"],
            "entries": [],
        }
    )
    listed: list[tuple[Entry, Progress]] = []
    for one in _list(fields["entries"]):
        if not isinstance(one, dict):
            raise TypeError(f"the entry {one!r} is no mapping")
        entry = dict(cast(dict[str, Any], one))
        state = entry.pop("state")
        number = entry.pop("round")
        request = entry.pop("request", None)
        arrived = entry.pop("ended", None)
        if (
            state not in STATES
            or isinstance(number, bool)
            or not isinstance(number, int)
            or number < 0
            or not isinstance(request, str | None)
            or isinstance(arrived, bool)
            or not isinstance(arrived, int | None)
        ):
            raise ValueError("an entry's state, round, request or ending does not read")
        progress = Progress(state, request, arrived, number)
        listed.append((read_entry(entry), progress))
    # sorted() is stable, as `Timetable` is, so each progress stays with its
    # entry.
    listed.sort(key=lambda pair: pair[0].at)
    positioning = _list(fields["positioning"])
    if (
        fields["phase"] not in PHASES
        or not isinstance(fields["record"], bool)
        or not all(isinstance(one, str) for one in positioning)
    ):
        raise ValueError("the phase, Record or a request id does not read")
    return State(
        replace(timetable, entries=tuple(entry for entry, _ in listed)),
        fields["phase"],
        fields["record"],
        positioning=tuple(positioning),
        progress=tuple(progress for _, progress in listed),
    )


def _list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{value!r} is no list")
    return cast(list[Any], value)


def _with(
    progress: tuple[Progress, ...], index: int, one: Progress
) -> tuple[Progress, ...]:
    """`progress` with `one` at position `index`."""
    return (*progress[:index], one, *progress[index + 1 :])


def _ruled(
    state: State, progress: tuple[Progress, ...]
) -> tuple[tuple[Progress, ...], list[int]]:
    """`progress` as the rule leaves it, and the positions of the entries to
    release now: the Next round, Due, Order, Turn-round and Skipped rules of
    the module's docstring. A skipped entry can move to its next round and
    be due there, so the rules are applied until nothing changes."""
    while True:
        ruled, release = _once(state, progress)
        if ruled == progress:
            return ruled, release
        progress = ruled


def _once(
    state: State, progress: tuple[Progress, ...]
) -> tuple[tuple[Progress, ...], list[int]]:
    """`_ruled` applied once: each entry in a final state whose next round
    has begun moves to it, then each entry that is `later` or `held` is
    ruled on in order of round and then position."""
    timetable = state.timetable
    assert timetable is not None
    clock = None if state.phase == LOADED else state.clock
    ruled = [
        (
            replace(one, state=LATER, request=None, round=one.round + 1)
            if clock is not None
            and one.state in FINAL
            and clock >= timetable.start + (one.round + 1) * timetable.repeat
            else one
        )
        for one in progress
    ]
    positions: dict[str, list[int]] = {}  # train -> the positions of its entries
    for index, entry in enumerate(timetable.entries):
        positions.setdefault(entry.train, []).append(index)
    release: list[int] = []
    waits: set[str] = set()  # the trains with an entry before this one not ended
    for index in sorted(range(len(ruled)), key=lambda one: (ruled[one].round, one)):
        entry, was = timetable.entries[index], ruled[index]
        train = entry.train
        if was.state == OUT:
            waits.add(train)
        if was.state not in (LATER, HELD):
            continue
        is_due = clock is not None and clock >= entry.at + was.round * timetable.repeat
        ruled[index] = replace(was, state=HELD if is_due else LATER)
        mine = positions[train]
        before = mine[mine.index(index) - 1]  # the last one, before the first
        if (
            clock is not None
            and is_due
            and state.phase == RUNNING
            and state.placed is not None
            and train not in waits
            and _stood(timetable, ruled, before, clock)
            and not (entry.turn and train in state.in_flight.values())
        ):
            if train not in state.placed:
                ruled[index] = replace(was, state=SKIPPED)
                continue
            release.append(index)
        waits.add(train)
    return tuple(ruled), release


def _stood(
    timetable: Timetable, progress: list[Progress], before: int, clock: int
) -> bool:
    """Whether the dwell of the train's entry before has passed: always,
    unless that entry ended by arrival less than its dwell ago."""
    arrived = progress[before].ended
    return arrived is None or clock >= arrived + timetable.entries[before].dwell * 60
