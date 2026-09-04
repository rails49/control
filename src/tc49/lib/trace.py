"""The trace tap: a bus subscriber that writes one JSONL line per event.

Per SYSTEM.md "The trace": subscribes ``tc49/#`` and writes each delivered
event flat, in canonical key order — ``time``, ``event``, then the payload
fields in inventory order — with ``time`` stamped from the run clock: float
seconds since the session started, simulated in batch and wall live
(ADR-0047). ``time`` is observation only — no payload carries a timestamp,
so no app can read one. A topic or payload field outside the inventory fails
loudly: the trace is load-bearing, and a stray field must break a test, not
rot quietly.

``event`` is the topic's leaf, which the inventory keeps unique — except on
a **device row**, where it is the key past ``tc49/layout/state/``: the
address is trailing levels a railroad's wiring decides, so a leaf there
would be an accessory number and the row it belongs to would be lost
(ADR-0043). ``_row`` is that one rule, and the two namespaces are one, so a
name still names one row.

That is a promise about what the *apps* write. The browser-writable topics
carry whatever a browser published, and an unreadable frame's only record is
its trace line — the dispatcher answers what it can address and drops the
rest (ADR-0034) — so the tap records those topics as they came: canonical
where it can be, verbatim where it cannot.
"""

import json
from typing import TextIO, cast

from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import (
    DEVICE_PREFIX,
    DEVICE_TOPICS,
    INBOUND,
    LEAF_FIELDS,
    leaf,
    split_device,
)


class TraceTap:
    def __init__(self, bus: Bus, out: TextIO, clock: Clock) -> None:
        self._out = out
        self._clock = clock
        bus.subscribe("tc49/#", self._record)

    def _record(self, topic: str, payload: Payload) -> None:
        event, fields = _row(topic)
        line: Payload = {"time": self._clock.now, "event": event}
        if topic in INBOUND:
            line.update(_as_given(payload, fields))
        else:
            for field in sorted(payload, key=fields.index):
                line[field] = payload[field]
        self._out.write(json.dumps(line, separators=(",", ":")) + "\n")


def _row(topic: str) -> tuple[str, tuple[str, ...]]:
    """What the line calls this event, and the fields it orders by.

    A device row is named by two levels where every other row is named by one
    (ADR-0043): the address is trailing levels a railroad's wiring decides, so
    the leaf of `tc49/layout/state/wanted/point/5` is `5` and says
    nothing, while the key past `tc49/layout/state/` is `wanted/point` and
    says which half of the vocabulary the line records. The two namespaces are
    one, so a name still tells one row from every other (`lib.inventory`).
    """
    device = split_device(topic)
    if device is None:
        name = leaf(topic)
        return name, LEAF_FIELDS[name]
    row, _address = device
    return row.removeprefix(DEVICE_PREFIX), DEVICE_TOPICS[row].fields


def _as_given(payload: object, fields: tuple[str, ...]) -> Payload:
    """What a client's frame contributes to its line: the inventory's fields
    in canonical order, then whatever else came with them in the order it
    came. A payload that is not an object has no fields at all, so the whole
    of it is the record."""
    if not isinstance(payload, dict):
        return {"payload": payload}
    given = cast(Payload, payload)  # JSON object keys are strings
    last = len(fields)  # everything the inventory does not name, in its wake
    order = sorted(given, key=lambda key: fields.index(key) if key in fields else last)
    return {key: given[key] for key in order}
