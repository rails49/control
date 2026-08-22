"""The event inventory: canonical payload field order per topic.

Mirrors the inventory table of SYSTEM.md. The trace's canonical key order
depends on this module; leaf names are globally unique across all topics
(tested), because the trace's ``event`` field is the leaf alone.

Where a field's *values* are a closed set the contract names, they live here
too, beside the field they belong to: ``run`` and ``power`` are those fields,
and their words are read by the apps that write them and by the payload
readers that refuse everything else.
"""

TOPICS: dict[str, tuple[str, ...]] = {
    "tc49/layout/boundary": ("boundary",),
    "tc49/layout/block_occupied": ("block",),
    "tc49/layout/block_vacated": ("block",),
    "tc49/layout/state/power": ("power",),
    "tc49/schedule/request_submitted": ("id", "train", "depart", "dest"),
    "tc49/schedule/state/exhausted": ("exhausted",),
    "tc49/schedule/state/facing": ("facing",),
    "tc49/ui/request_wanted": ("train", "dest"),
    "tc49/ui/reversal_wanted": ("train",),
    "tc49/ui/run_wanted": ("run",),
    "tc49/ui/placement_wanted": ("train", "block"),
    "tc49/dispatch/request_admitted": ("id", "dest", "pruned"),
    "tc49/dispatch/request_rejected": ("id", "reason"),
    "tc49/dispatch/request_completed": ("id",),
    "tc49/dispatch/route_chosen": ("id", "route", "k_tried"),
    "tc49/dispatch/move_granted": ("id", "train", "transit", "into", "aspect"),
    "tc49/dispatch/grant_refused": ("id", "reason", "obstacles"),
    "tc49/dispatch/lock_granted": ("train", "resources"),
    "tc49/dispatch/lock_released": ("train", "resources"),
    "tc49/dispatch/train_placed": ("train", "block"),
    "tc49/dispatch/state/run": ("run",),
    "tc49/dispatch/state/aspects": ("aspects",),
    "tc49/dispatch/state/disputed": ("trains", "blocks"),
    "tc49/dispatch/state/allocation": ("trains", "crossing", "locks", "requests"),
    "tc49/dispatch/align": ("connection", "transit", "points"),
    "tc49/drive/cross": ("train", "connection", "transit", "into"),
}


HELD = "held"
RUNNING = "running"
"""The two values of ``tc49/dispatch/state/run``. A word and not a boolean:
the ordinary-shutdown drain adds ``draining`` as a third value here rather
than inventing a state of its own (#123). Not to be read as the ``held``
``grant_refused`` reason, which says a resource is locked by another train
and is a different thing on a different topic (CONTEXT.md)."""


ON = "on"
STOPPED = "stopped"
OFF = "off"
"""The three values of ``tc49/layout/state/power``: the layout's answer to
whether a train may move at all. `stopped` is an **emergency stop** — every
locomotive told to stand with the track still live — and `off` is the supply
removed. They differ for the person recovering, who clears one and switches
the other back on, and not for the dispatcher, which branches on "not `on`"
(ADR-0041). `stopped` and not `stop`, which is an aspect: a different thing
on a different topic."""


def is_state_topic(topic: str) -> bool:
    """Whether a topic is a state topic, read off the path: state is marked
    structurally by a ``state`` segment before the leaf, so the split is a
    property of the name and not a list to keep (SYSTEM.md, rule 2)."""
    levels = topic.split("/")
    return len(levels) >= 2 and levels[-2] == "state"


INBOUND = frozenset(
    topic
    for topic in TOPICS
    if topic.startswith("tc49/ui/") and not is_state_topic(topic)
)
"""The topics a client writes: the panel's write surface, and what a broker's
ACL will grant it once the bridge is gone (ADR-0034). Named here rather than
in the bridge because the fact outlives the relay, and read off the role
rather than listed, `tc49/ui/*` being what the ACL would name — a topic under
`ui` is one a person's page writes, that being what the role means
(ADR-0035).

Event topics only. A `ui` role with concurrent instances may not write a state
topic at all (ADR-0035), and the bridge relies on it besides: a client's frame
is published from that client's own handler thread, and publishing a state
topic would write the bus's last-value map from there. So a `tc49/ui/state/…`
leaf added to the table above stays outbound, and the bridge refuses it.

Gestures, never requests: `tc49/schedule/request_submitted` is refused
inbound like any other topic, which is what makes the scheduler's
single-minter claim something the topic check enforces (ADR-0036)."""


def leaf(topic: str) -> str:
    return topic.rsplit("/", 1)[-1]


LEAF_FIELDS: dict[str, tuple[str, ...]] = {
    leaf(topic): fields for topic, fields in TOPICS.items()
}
