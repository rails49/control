"""The scenario document: placement and requests.

One of the coarse document types of ADR-0010, alongside
:class:`~tc49.lib.layout.Layout` and :class:`~tc49.lib.roster.Roster`. The
types live here rather than in the store because they are the shared
vocabulary every app reads; the store owns the binding and the validator that
produce them.

A scenario says where the railroad's trains **start**, not what they are: the
trains themselves are the railroad's roster and a train's length is written
there (ADR-0039). A scenario placing no train at all is a run that comes up
with an empty layout, which is an ordinary cold start rather than a fault.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrainSpec:
    """Where a scenario stands one of its railroad's trains. The train is the
    roster's and so is its length; this is the placement alone."""

    at: str  # starting block
    facing: str  # 'A' or 'B': the end of `at` it would depart through nose-first


@dataclass(frozen=True)
class RequestSpec:
    train: str
    depart: str  # '<block>.<end>', or a bare end letter for chained requests
    arrivals: tuple[str, ...]  # arrival ends: '<block>.<end>' or bare '<block>'


@dataclass(frozen=True)
class Scenario:
    name: str
    layout: str
    trains: dict[str, TrainSpec]
    requests: tuple[RequestSpec, ...]
