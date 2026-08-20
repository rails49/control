"""The event inventory: canonical payload field order per topic.

Mirrors the inventory table of SYSTEM.md. The trace's canonical key order
depends on this module; leaf names are globally unique across all topics
(tested), because the trace's ``event`` field is the leaf alone.
"""

TOPICS: dict[str, tuple[str, ...]] = {
    "tc49/layout/boundary": ("boundary",),
    "tc49/layout/block_occupied": ("block",),
    "tc49/layout/block_vacated": ("block",),
    "tc49/schedule/request_submitted": ("id", "train", "depart", "dest"),
    "tc49/schedule/state/exhausted": ("exhausted",),
    "tc49/schedule/state/facing": ("facing",),
    "tc49/ui/request_wanted": ("train", "dest"),
    "tc49/dispatch/request_admitted": ("id", "dest", "pruned"),
    "tc49/dispatch/request_rejected": ("id", "reason"),
    "tc49/dispatch/request_completed": ("id",),
    "tc49/dispatch/route_chosen": ("id", "route", "k_tried"),
    "tc49/dispatch/move_granted": ("id", "train", "transit", "into", "aspect"),
    "tc49/dispatch/grant_refused": ("id", "reason", "obstacles"),
    "tc49/dispatch/lock_granted": ("train", "resources"),
    "tc49/dispatch/lock_released": ("train", "resources"),
    "tc49/dispatch/state/aspects": ("aspects",),
    "tc49/dispatch/state/allocation": ("trains", "locks", "requests"),
    "tc49/dispatch/align": ("connection", "transit", "points"),
    "tc49/drive/cross": ("train", "connection", "transit", "into"),
}


INBOUND = "tc49/ui/request_wanted"
"""The one topic a client writes: the panel's whole write surface, and what
a broker's ACL will grant it once the bridge is gone (ADR-0034). Named here
rather than in the bridge because the fact outlives the relay.

A gesture, never a request: `tc49/schedule/request_submitted` is refused
inbound like any other topic, which is what makes the scheduler's
single-minter claim something the topic check enforces (ADR-0036)."""


def leaf(topic: str) -> str:
    return topic.rsplit("/", 1)[-1]


LEAF_FIELDS: dict[str, tuple[str, ...]] = {
    leaf(topic): fields for topic, fields in TOPICS.items()
}
