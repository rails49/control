"""The lock table and the questions asked of it (#1315).

`Table` holds where each train is recorded, what it occupies and holds, the
route it runs, the moves whose readings are still expected, each sensor's
latest reading and the sensors not reporting. The questions read it and write
nothing. The dispatcher keeps the current table and is its one writer (#761);
the locking strategies read it through `locking.ReadOnlyState`.

It imports `tc49.lib` and nothing else of the dispatcher.
"""

from dataclasses import dataclass, field, replace

from tc49.lib.inventory import Refusal
from tc49.lib.layout import Layout, block_of


@dataclass(frozen=True)
class Route:
    blocks: tuple[str, ...]  # origin .. arrival block
    transits: tuple[str, ...]  # qualified ids, one per block pair

    @property
    def arrival_block(self) -> str:
        return self.blocks[-1]

    def crossing_order(self) -> list[str]:
        """The resources beyond the origin, in the order crossed."""
        result: list[str] = []
        for transit, block in zip(self.transits, self.blocks[1:]):
            result += [transit, block]
        return result

    def interleaved(self) -> list[str]:
        """The alternating block/transit sequence, for the route_chosen event."""
        return [self.blocks[0], *self.crossing_order()]


@dataclass(frozen=True)
class Move:
    from_block: str
    transit: str
    into: str
    locked: list[str]  # resources newly locked for this move; [] under FullRoute
    # The second increment, when it was obtained: a separate grant, published
    # as its own lock_granted so a grant stays one transit with its far block
    # (ADR-0029). Empty means it was not obtained, which is the `caution`
    # aspect rather than an error.
    ahead: list[str]


@dataclass
class Active:
    request_id: str  # the request it runs, which the dispatcher keeps
    route: Route
    cur_index: int  # index into route.blocks of cur(t)
    outstanding: Move | None  # granted move whose head is not yet in its block


@dataclass(eq=False)
class Following:
    """A move whose readings are still expected (#1171). It outlives the
    request, since a reading can arrive after the request has ended. For a move
    out of block X through end `e`, over transit T, into block Y through end
    `f`: `exit` is `X.e`, `entry` is `Y.f` and `far` is the end of Y opposite
    `f`."""

    move: Move
    exit: str
    entry: str
    far: str
    exit_read: bool = False  # `exit` has read occupied, at the grant or since
    head_in: bool = False  # `entry` or `far` has read occupied
    at_far: bool = False  # `far` has read occupied


def transit_blocks(layout: Layout, transit: str) -> set[str]:
    """The two blocks a transit (as 'connection.transit') joins, or none where
    the drawing has no such transit: a crossing hint is restored from a picture
    that may be older than the drawing (ADR-0071)."""
    connection, _, name = transit.partition(".")
    held = layout.connections.get(connection)
    if held is None or name not in held.transits:
        return set()
    return {block_of(end) for end in held.transits[name]}


@dataclass
class Table:
    # Read by `obstacle` for the conflict matrix and by `transit_blocks`. Left
    # out of equality and hashing, so every table of one railroad shares it.
    layout: Layout = field(compare=False)
    locks: dict[str, str]  # resource -> holding train
    block_of: dict[str, str]  # train -> block it stands in (or last parked)
    active: dict[str, Active]
    # train -> the end it will leave by once the last route committed for it
    # is done. Written when a route is chosen, since a route is fixed from
    # then on (ADR-0002), and so already true of a train still running one.
    departure: dict[str, str] = field(default_factory=dict[str, str])
    # train -> the transit it is crossing: written at the grant, dropped when
    # the head is in, and so exactly the trains with an outstanding move.
    # `block_of` goes on naming the block the train left until its tail is out
    # of it or its head is in the next, so this is the whole of what says a
    # train is between two blocks rather than standing in one (#123). It
    # restores across a restart with no route behind it, which is what makes it
    # a placement hint and not a resumed move.
    crossing: dict[str, str] = field(default_factory=dict[str, str])
    # sensor `<block>.<end>` -> whether it last read occupied: the level each
    # one last settled at (`state/settled/sensor`), which is what makes an
    # at-least-once repeat a no-op (ADR-0047), and what the dispute check
    # compares (#153). Only sensors a row has spoken for are keys — silence is
    # not a clear reading, and a binding that reports nothing disputes nothing
    # rather than the whole railroad.
    readings: dict[str, bool] = field(default_factory=dict[str, bool])
    # train -> the blocks and transits it occupies, tail to head, for each
    # placed train. A lock on no list is held ahead. A placed train's list holds
    # `block_of[train]`, unless the train is `crossing` with the block it left
    # already released (#1171).
    occupied: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    # train -> the moves whose readings are still expected, oldest first.
    following: dict[str, list[Following]] = field(
        default_factory=dict[str, list[Following]]
    )
    # What a train taken off the layout still holds, because a sensor last read
    # occupied (ADR-0069): each block, and each transit on its `occupied` list
    # while either of that transit's blocks is here. The lock table names the
    # holder; this is what says the lock waits for a clear reading rather
    # than for a move, so that reading is explained (#1164).
    residue: set[str] = field(default_factory=set[str])
    # The sensors `layout` last listed as not reporting, `<block>.<end>`
    # (`state/unknown_sensors`). Empty until a row says otherwise: no row means
    # none, and a binding with no sensors lists none. Written only by that row,
    # so a sensor returning takes its block straight back into use, with no press.
    unknown_sensors: frozenset[str] = frozenset()
    # Whether `layout` last said the railroad runs without sensors
    # (`state/settings`, #1314). While it does, readings are ignored: no block
    # is out of use or disputed and none reads occupied, a launch locks its
    # whole route and no move is granted. `False` until a row says otherwise.
    without_sensors: bool = False

    @property
    def out_of_use(self) -> frozenset[str]:
        """The blocks either of whose sensors is listed (#1152). The dispatcher
        grants nothing into, out of or through one, and a train already on a
        route through one waits at its signal, keeping its route (ADR-0002).
        Placing does not ask: `free` and `_judged` answer as they did, and a
        placement on a block out of use is accepted. This covers the sensor
        cause; GLOSSARY.md, **Out of use**, lists every cause. None while the
        railroad runs without sensors."""
        if self.without_sensors:
            return frozenset()
        return frozenset(block_of(sensor) for sensor in self.unknown_sensors)

    def reads_occupied(self, block: str) -> bool:
        """Whether either of the block's sensors last read occupied; never
        while the railroad runs without sensors."""
        return not self.without_sensors and (
            self.readings.get(f"{block}.A") is True
            or self.readings.get(f"{block}.B") is True
        )

    @property
    def disputed_blocks(self) -> frozenset[str]:
        """The blocks that read occupied with no train explaining the reading
        (`disputed`, #1164, #1171); none while the railroad runs without
        sensors."""
        if self.without_sensors:
            return frozenset()
        explained = set(self.residue)
        for listed in self.occupied.values():
            explained.update(listed)
        for active in self.active.values():
            if active.outstanding is not None:
                explained.add(active.outstanding.into)
        for train, transit in self.crossing.items():
            active = self.active.get(train)
            if active is None or active.outstanding is None:
                explained |= transit_blocks(self.layout, transit)
        return frozenset(
            block_of(sensor)
            for sensor, occupied in self.readings.items()
            if occupied and block_of(sensor) not in explained
        )

    def obstacle(self, resource: str, train: str) -> tuple[str, str, str] | None:
        """Why `train` cannot lock `resource`: (reason, resource, holder),
        or None if it can. Transits also require no conflicting locked
        transit at their connection (instantaneous admissibility).

        A block that reads occupied is not entered, whoever holds it, the
        train's own residue included (ADR-0077): a cut of cars would be hit,
        and a stuck detector takes the block out of use until it reads clear.
        A block out of use by a sensor not reporting answers the same (#1152).
        The holder is "" for a disputed block or a block out of use, whoever
        holds its lock, since what stops the train is a sensor and not a
        train (#1164, #1254); "" for `train`'s own residue; and otherwise
        whoever holds it, "" where nobody does."""
        if self.reads_occupied(resource) or resource in self.out_of_use:
            holder = self.locks.get(resource, "")
            if (
                holder == train
                or resource in self.disputed_blocks
                or resource in self.out_of_use
            ):
                holder = ""
            return (Refusal.HELD, resource, holder)
        holder = self.locks.get(resource)
        if holder is not None and holder != train:
            return (Refusal.HELD, resource, holder)
        if "." in resource:  # a transit: check the conflict matrix
            for locked, by in sorted(self.locks.items()):
                if (
                    by != train
                    and "." in locked
                    and self.layout.conflicts(resource, locked)
                ):
                    return (Refusal.TRANSIT_CONFLICT, locked, by)
        return None

    def free(self, block: str, train: str | None = None) -> bool:
        """Whether nothing at all has a claim on `block`.

        Both claims a route carries, not just the stronger one: a resource is
        **committed** when it is on a route the dispatcher has chosen and not
        yet locked, and that is a claim (GLOSSARY.md). Under `FullRoute` the
        two sets coincide, since a launch locks the whole route; under
        `Incremental` a fixed route runs on ahead of its locks, and reading
        the lock table alone would call those blocks free.

        Placing a train into one strands the request that owns it: the route
        is fixed (ADR-0002), and the placed train is idle, so its standing
        lock is a permanent obstacle (SAFETY.md) and the committed train is
        refused `unsafe` at every sweep for the rest of the session.

        `train` asking, the block is judged as its placement will leave the
        railroad: its own requests cancelled (ADR-0049), which happens only
        once the placement is accepted (#1062). So its own route is no claim,
        and of the locks it holds only the one it stands on stays. What is
        left is another train's claim, which a placement may not walk into.
        A block it still holds as residue of its own removal is free to it
        (ADR-0069): the claim is its own, and putting it back there is the
        person saying the loco never left.
        """
        holder = self.locks.get(block)
        if holder is not None and holder != train:
            return False
        if (
            holder is not None
            and block == self.block_of.get(holder)
            and block not in self.residue
        ):
            return False
        return not any(
            block in active.route.blocks[active.cur_index :]
            for owner, active in self.active.items()
            if owner != train
        )

    def standing_still(self) -> list[str]:
        """The blocks that read occupied and that nobody holds or that are
        residue, since nothing is granted into them until they read clear
        (ADR-0077), and the blocks out of use, until their sensors return (#1152):
        obstacles as permanent as an idle train's block. None while the railroad
        runs without sensors, whose readings are ignored (#1314)."""
        if self.without_sensors:
            return []
        occupied = {block_of(s) for s, reading in self.readings.items() if reading}
        return sorted(
            self.out_of_use
            | {
                block
                for block in occupied
                if block not in self.locks or block in self.residue
            }
        )

    def moving(self, overdue: frozenset[str], held: frozenset[str]) -> bool:
        """Whether a power cut now would strand something: any train with a
        move between its grant and its entry sensor clearing or its far sensor
        reading occupied (#1171), other than one no throttle holds with both
        those sensors unknown: `layout` has stopped it, and a person's off
        press has to be able to drain past it (#1152, GLOSSARY.md,
        **Moving**). A train `state/taken` names (`held`) counts with both
        unknown, since `layout` leaves it running under its throttle, and the
        drain waits until the person lets go of it or presses the stop sign
        (#1187). A train standing in a block loses
        nothing when the supply goes, whether or not it is active: one a drain
        stopped at a signal partway along its route keeps that route and its
        locks, and carries on once power reads `on` again (ADR-0078). A
        **crossing** train counts with no request behind it: a restored hint,
        or one a change of `without_sensors` left (#1321), is a train the
        dispatcher believes is between two blocks, and a drain
        that ended over one would have `layout` cut the supply under it.
        A train on `state/overdue` (`overdue`) does not count, by any move or
        hint: `layout` has stopped it for not arriving within its allowance,
        and it stands until it arrives, a throttle takes it, or it is placed or
        removed (#1191, GLOSSARY.md, **Moving**).

        Nothing is moving while the railroad runs without sensors: no move is
        followed, so a drain ends at once (#1314).
        """
        if self.without_sensors:
            return False
        listed = self.unknown_sensors
        return any(
            not each.at_far
            and (train in held or not (each.entry in listed and each.far in listed))
            for train, following in self.following.items()
            if train not in overdue
            for each in following
        ) or any(
            not self.following.get(train)
            for train in self.crossing
            if train not in overdue
        )

    def newest(self, train: str) -> Following | None:
        """The train's newest move whose readings are still expected."""
        following = self.following.get(train)
        return following[-1] if following else None


def locked_ahead(state: Table, train: str, route: Route, standing: int) -> int:
    """How many blocks of `route` past index `standing` are locked to `train`
    with the transit into them and may be entered, counted until the first
    that is not locked with its transit, is out of use or is disputed, and
    none at all where `standing` is out of use, since no train is let out of
    one (#1152, #1160, #1164). A block locked without its transit is one the
    train occupies, not one it holds ahead (#1230)."""
    out = state.out_of_use
    disputes = state.disputed_blocks
    if route.blocks[standing] in out:
        return 0
    depth = 0
    for block, transit in zip(
        route.blocks[standing + 1 :], route.transits[standing:], strict=True
    ):
        if (
            state.locks.get(block) != train
            or state.locks.get(transit) != train
            or block in out
            or block in disputes
        ):
            break
        depth += 1
    return depth


def broken(state: Table) -> list[str]:
    """The lock table's rules that `state` breaks, one line each and sorted,
    so equal states give equal lists (#761). Reads and writes nothing else.

    The rules are what the maps — `locks`, `block_of`, `crossing`, `occupied`
    and `residue` — keep between them at the end of an event: a placed train
    holds the lock on its block; every lock is a placed train's or residue;
    every entry on a train's `occupied` list is locked to it; an idle train
    holds its block, its residue and its `occupied` list and nothing more;
    residue is locked, and a block in it has a sensor reading occupied or
    listed, with nobody standing there; an active train is placed, and holds
    and is crossing what its outstanding move took; a crossing train is placed;
    and no two trains' locked transits conflict (ADR-0006).

    The dispatcher drains the railroad on a rule newly broken (ADR-0076,
    ADR-0078). `safe()`
    is not among them: its cost grows exponentially with the active trains
    (ADR-0003).
    """
    lines: list[str] = []
    placed = state.block_of
    out_of_use = state.out_of_use
    for train, block in placed.items():
        holder = state.locks.get(block)
        if holder != train:
            lines.append(
                f"{train} stands in {block}, which is locked to {holder or 'nobody'}"
            )
    for resource, holder in state.locks.items():
        if holder not in placed and resource not in state.residue:
            lines.append(f"{resource} is locked to {holder}, which is not placed")
    for train, listed in state.occupied.items():
        for entry in listed:
            holder = state.locks.get(entry)
            if holder != train:
                lines.append(
                    f"{train} occupies {entry}, which is locked to {holder or 'nobody'}"
                )
    for resource, holder in state.locks.items():
        if (
            holder in placed
            and holder not in state.active
            and resource != placed[holder]
            and resource not in state.residue
            and resource not in state.occupied.get(holder, ())
        ):
            lines.append(f"{holder} is idle and holds {resource}")
    for resource in state.residue:
        holder = state.locks.get(resource)
        if holder is None:
            lines.append(f"{resource} is residue and not locked")
        elif resource in state.layout.blocks:
            if not state.reads_occupied(resource) and resource not in out_of_use:
                lines.append(f"{resource} is {holder}'s residue and not read occupied")
            if placed.get(holder) == resource:
                lines.append(f"{resource} is {holder}'s residue and it stands there")
        elif not any(
            block in state.residue and state.locks.get(block) == holder
            for block in transit_blocks(state.layout, resource)
        ):
            lines.append(f"{resource} is {holder}'s residue with neither block kept")
    for train, active in state.active.items():
        if train not in placed:
            lines.append(f"{train} is active and not placed")
        move = active.outstanding
        if move is None:
            if train in state.crossing:
                lines.append(f"{train} has no move and is crossing")
            continue
        for resource in (move.transit, move.into):
            if state.locks.get(resource) != train:
                lines.append(f"{train} is moving through {resource} and not holding it")
        if state.crossing.get(train) != move.transit:
            lines.append(
                f"{train} is moving through {move.transit} and not crossing it"
            )
    for train in state.crossing:
        if train not in placed:
            lines.append(f"{train} is crossing and not placed")
    transits = sorted(
        (resource, holder)
        for resource, holder in state.locks.items()
        if "." in resource
    )
    for i, (one, by) in enumerate(transits):
        for other, also in transits[i + 1 :]:
            if by != also and state.layout.conflicts(one, other):
                lines.append(f"{one} locked to {by} conflicts with {other} of {also}")
    return sorted(lines)


# -- what a transition returns for the dispatcher to publish -----------------


@dataclass(frozen=True)
class Disputed:
    """The blocks the sensors dispute once a reading is recorded and before
    any move takes it (`Table.disputed_blocks`), for `state/disputed`."""

    blocks: frozenset[str]


@dataclass(frozen=True)
class Released:
    """Locks `train` has given up, for one `lock_released` naming them in
    this order."""

    train: str
    resources: tuple[str, ...]


@dataclass(frozen=True)
class HeadIn:
    """The head of `train` is in `block`, the block its move entered. The
    dispatcher publishes the aspects and the allocation here, before any grant
    that follows: the scheduler moves the train's facing when the allocation
    names it in the block its move entered, and `layout` reads that facing for
    the next `move` (#1025, #1038, ADR-0052)."""

    train: str
    block: str


@dataclass(frozen=True)
class MoveEnded:
    """The newest move of `train` has ended, at its entry sensor reading
    `clear` or its far sensor reading `occupied`. What its request does is the
    dispatcher's to decide."""

    train: str


Effect = Disputed | Released | HeadIn | MoveEnded


# -- the transitions ----------------------------------------------------------


def reading(table: Table, sensor: str, occupied: bool) -> tuple[Table, list[Effect]]:
    """A sensor's settled reading (ADR-0047), taken against every move still
    expecting that sensor, oldest first. A reading changes the table only for
    the move that expects it, and a person backing a train at a platform
    changes nothing (GOALS.md).

    A sensor reports presence, which is a level: a reading that repeats what
    `readings` holds is an at-least-once repeat, and the table comes back as
    given with no effect. A changed reading is recorded, and its first effect
    is `Disputed`. The table given is left unchanged."""
    if table.readings.get(sensor) == occupied:
        return table, []
    new = _copied(table)
    new.readings[sensor] = occupied
    effects: list[Effect] = [Disputed(new.disputed_blocks)]
    for train, following in new.following.items():
        for each in list(following):
            effects += _followed(new, train, each, sensor, occupied)
    return new, effects


def not_reporting(table: Table, sensors: frozenset[str]) -> tuple[Table, list[Effect]]:
    """The sensors `layout` lists as not reporting (`state/unknown_sensors`).
    A block with one is out of use (#1152). A list equal to the one held
    changes nothing, and the table comes back as given. The table given is
    left unchanged."""
    if sensors == table.unknown_sensors:
        return table, []
    return replace(table, unknown_sensors=sensors), []


def _copied(table: Table) -> Table:
    """A copy of `table` whose maps a reading may change are its own (#1330
    freezes the table)."""
    return replace(
        table,
        locks=dict(table.locks),
        block_of=dict(table.block_of),
        active={train: replace(each) for train, each in table.active.items()},
        crossing=dict(table.crossing),
        readings=dict(table.readings),
        occupied={train: list(listed) for train, listed in table.occupied.items()},
        following={
            train: [replace(each) for each in listed]
            for train, listed in table.following.items()
        },
    )


def _followed(
    table: Table, train: str, each: Following, sensor: str, occupied: bool
) -> list[Effect]:
    """A changed reading, taken against one move that may expect it (#1171).

    For a move out of X through `exit`, over T, into Y through `entry`:
    `exit` occupied then clear is the tail out of X, or occupied at the grant
    and then clear; `entry` occupied is the head in Y, and so is `far` where
    `entry` was `unknown` as the train passed; `entry` then clear is the whole
    train in Y; `far` occupied is where it stops. Anything else changes
    nothing, and a clear reading is never taken for a train gone: a short
    train stands between its block's sensors and both read clear.

    A request ends when the whole train is in its last block, or when the far
    sensor reads `occupied` if the entry sensor was not seen to clear
    (GOALS.md): the newest move ending is `MoveEnded`."""
    newest = table.newest(train) is each
    effects: list[Effect] = []
    if occupied:
        if sensor == each.exit:
            each.exit_read = True
        elif sensor in (each.entry, each.far):
            if not each.head_in:
                effects += _head_in(table, train, each)
            if sensor == each.far:
                each.at_far = True
                if newest:
                    effects.append(MoveEnded(train))
    elif sensor == each.exit:
        if each.exit_read:
            effects += _tail_out(table, train, each)
    elif sensor == each.entry and each.head_in:
        effects += _tail_in(table, train, each)
        if newest:
            effects.append(MoveEnded(train))
    return effects


def _head_in(table: Table, train: str, each: Following) -> list[Effect]:
    """Y's sensor at the end the train enters by reads `occupied`: the head is
    in Y, and the train may be granted its next move (GOALS.md).

    The move is no longer outstanding, and the train is no longer crossing. Y
    goes to the head of what the train occupies, from wherever a move back
    over a transit left it, and the train is recorded in Y, past the signal
    it left by, which now shows `stop` (ADR-0093)."""
    into = each.move.into
    each.head_in = True
    active = table.active.get(train)
    if active is not None:
        active.outstanding = None
    table.crossing.pop(train, None)
    occupying = table.occupied[train]
    if into in occupying:
        occupying.remove(into)
    occupying.append(into)
    table.block_of[train] = into
    return [HeadIn(train, into)]


def _tail_out(table: Table, train: str, each: Following) -> list[Effect]:
    """X's sensor at the end the train leaves by reads `occupied`, then
    `clear`: the tail has left X, and X is released (GOALS.md).

    The train is recorded in the block it is crossing into if it was still
    recorded in X. A move older than this one into X is dropped, so another
    train entering X later reads nothing for this one."""
    left = each.move.from_block
    occupying = table.occupied[train]
    if left not in occupying:
        return []
    effects = _give_up(table, train, [left])
    if table.block_of[train] == left:
        table.block_of[train] = each.move.into
    following = table.following[train]
    older = following[: following.index(each)]
    following[: len(older)] = [m for m in older if m.move.into != left]
    return effects


def _tail_in(table: Table, train: str, each: Following) -> list[Effect]:
    """Y's sensor at the end the train entered by reads `clear` after the head
    is in: the whole train is in Y, and T is released, with anything of that
    train's still held behind it (GOALS.md), in one `Released`.

    A transit a later move has taken again is not this one's to give up, nor
    is a block on the train's route ahead whose transit in is locked to it
    (#1230). This move and any older are no longer followed."""
    occupying = table.occupied[train]
    transit = each.move.transit
    effects: list[Effect] = []
    if transit in occupying:
        entered = _entered_ahead(table, train)
        behind = occupying[: occupying.index(transit) + 1]
        effects = _give_up(table, train, [r for r in behind if r not in entered])
    following = table.following[train]
    del following[: following.index(each) + 1]
    return effects


def _entered_ahead(table: Table, train: str) -> set[str]:
    """The blocks on the train's route from the one it is granted into on,
    each with the transit into it locked to the train."""
    active = table.active.get(train)
    if active is None:
        return set()
    route = active.route
    return {
        route.blocks[i]
        for i in range(max(active.cur_index, 1), len(route.blocks))
        if table.locks.get(route.transits[i - 1]) == train
    }


def _give_up(table: Table, train: str, resources: list[str]) -> list[Effect]:
    """What a train has left behind it, off its list and released."""
    occupying = table.occupied[train]
    for resource in resources:
        occupying.remove(resource)
        if table.locks.get(resource) == train:
            del table.locks[resource]
    return [Released(train, tuple(resources))]
