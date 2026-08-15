"""The event inventory: canonical payload field order per topic.

Mirrors the inventory table of SYSTEM.md. The trace's canonical key order
depends on this module; leaf names are globally unique across all topics
(tested), because the trace's ``event`` field is the leaf alone.
"""

TOPICS: dict[str, tuple[str, ...]] = {
    "tc49/layout/tick": ("tick",),
    "tc49/layout/block_occupied": ("block",),
    "tc49/layout/block_vacated": ("block",),
    "tc49/schedule/request_submitted": ("id", "train", "depart", "dest"),
    "tc49/schedule/state/exhausted": ("exhausted",),
    "tc49/dispatch/request_admitted": ("id", "dest", "pruned"),
    "tc49/dispatch/request_rejected": ("id", "reason"),
    "tc49/dispatch/request_completed": ("id",),
    "tc49/dispatch/route_chosen": ("id", "route", "k_tried"),
    "tc49/dispatch/move_granted": ("id", "train", "transit", "into"),
    "tc49/dispatch/grant_refused": ("id", "reason", "obstacles"),
    "tc49/dispatch/lock_granted": ("train", "resources"),
    "tc49/dispatch/lock_released": ("train", "resources"),
    "tc49/drive/align": ("connection", "transit"),
    "tc49/drive/cross": ("train", "connection", "transit", "into"),
}


def leaf(topic: str) -> str:
    return topic.rsplit("/", 1)[-1]


LEAF_FIELDS: dict[str, tuple[str, ...]] = {
    leaf(topic): fields for topic, fields in TOPICS.items()
}
