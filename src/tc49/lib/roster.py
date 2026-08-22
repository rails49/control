"""The roster document: the trains a railroad owns.

A railroad's roster is every train it owns, whether on the layout or off it
(CONTEXT.md, **Roster**). Being on it is what makes a train **known**, which
is separate from being **placed** — a railroad at rest says what stock it has
without saying where any of it stands
([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)).

A train is a name and a length, and nothing else is decided here: cars, types,
DCC addresses, priority, and the trains that split and merge during operation
are `scratch/4-stock`'s design and add fields to :class:`Train` when they
land ([#170](https://github.com/rails49/control/issues/170)).

The type lives here beside :mod:`tc49.lib.scenario` for the same reason that
one does: it is the shared vocabulary every app reads, and the store owns the
binding and the validator that produce it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Train:
    """One train the railroad owns. A name and a length, the name being the
    key it is held under."""

    length: int


@dataclass(frozen=True)
class Roster:
    """A railroad's stock: the trains it owns, by name.

    Owned by the railroad rather than by a run, so one roster serves every
    scenario over that railroad — which is what makes a train's length one
    fact rather than one per scenario. A scenario says where a train starts;
    how long it is, is here.
    """

    railroad: str
    trains: dict[str, Train]

    def lengths(self) -> dict[str, int]:
        """Train to length, which is the whole of what the dispatcher's fit
        check and its `unknown_train` answer read a roster for."""
        return {name: train.length for name, train in self.trains.items()}
