"""Why a request ended without arriving: the one set every reader answers to.

A request ends by arrival, by rejection before admission, or by
**cancellation** (ADR-0049). The third is this module. The dispatcher is the
only app that mints a cancellation reason, and every reader of one — the
scheduler dropping the request, the metrics counting it, a panel wording it —
has to know the same names, so they live here rather than as bare literals at
each call site, exactly as the rejection reasons do
(`tc49.lib.rejection`, #126).

The names alone. What a cancellation *tells a reader* is wording, and wording
belongs to the panel (ui/PANEL.md).

A `StrEnum` because the value crosses the bus: inside Python every call site
names a member and is type-checked, while on the wire a member is its own name
and a browser reads a plain string (ADR-0008).

Not a rejection reason with a new name. A rejection is admission refusing to
queue a request at all, and it is an answer to the submitter; a cancellation
retires a request the dispatcher had already accepted, and is a fact about
work that was under way. Two events, two sets — one component's answer never
has to be read against the other's.
"""

from enum import StrEnum


class Reason(StrEnum):
    """Why the dispatcher retired a request without the train arriving, in
    the order the gesture that causes each reaches it: a person revoked the
    request itself, or a person said where the train actually is and that
    statement retired the request under it — off the layout, or standing in
    some other block.

    `removed` and `displaced` are one gesture in two directions
    (ADR-0039), and they are kept apart because they leave the railroad in
    different places: a removed train is off the rails and holds nothing, a
    displaced one stands somewhere and holds that block.
    """

    REVOKED = "revoked"
    REMOVED = "removed"
    DISPLACED = "displaced"
