"""The trace tap: a bus subscriber that writes one JSONL line per event.

Per SYSTEM.md "The trace": subscribes ``tc49/#`` and writes each delivered
event flat, in canonical key order — ``tick``, ``event`` (the topic's
leaf), then the payload fields in inventory order — with ``tick`` stamped
from the last tick event observed, ``0`` before the first. A topic or
payload field outside the inventory fails loudly: the trace is
load-bearing, and a stray field must break a test, not rot quietly.
"""

import json
from typing import TextIO

from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import LEAF_FIELDS, leaf


class TraceTap:
    def __init__(self, bus: Bus, out: TextIO) -> None:
        self._out = out
        self._tick = 0
        bus.subscribe("tc49/#", self._record)

    def _record(self, topic: str, payload: Payload) -> None:
        event = leaf(topic)
        if event == "tick":
            self._tick = payload["tick"]
        line: Payload = {"tick": self._tick, "event": event}
        fields = LEAF_FIELDS[event]
        for field in sorted(payload, key=fields.index):
            line[field] = payload[field]
        self._out.write(json.dumps(line, separators=(",", ":")) + "\n")
