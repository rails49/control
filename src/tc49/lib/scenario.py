"""The scenario document: stock and requests.

One of the two coarse document types of ADR-0010, alongside
:class:`~tc49.lib.layout.Layout`. The types live here rather than in the
store because they are the shared vocabulary every app reads; the store owns
the binding and the validator that produce them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrainSpec:
    length: int
    at: str  # starting block


@dataclass(frozen=True)
class RequestSpec:
    train: str
    depart: str  # '<block>.<end>', or a bare end letter for chained requests
    arrivals: tuple[str, ...]  # arrival ends: '<block>.<end>' or bare '<block>'
    at: int


@dataclass(frozen=True)
class Scenario:
    name: str
    layout: str
    trains: dict[str, TrainSpec]
    requests: tuple[RequestSpec, ...]
