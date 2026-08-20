"""Why a request was rejected: one set, both sides answering to it (#126).

The dispatcher is the only app that mints a rejection reason, and every
reader of one — the panel first — has to know the same names. Minted as bare
literals at each call site, the set was something nobody held: #107 landed a
reason the panel could not spell, and nothing failed. So the names live here,
where the dispatcher takes them from and the UI's copy is generated from
(`rejection.generated.ts`, written by `tc49 generate`) rather than kept by
hand, the way the symbol library already is (ADR-0022).

The names alone. What a rejection *tells a reader* is wording, and wording
belongs to the panel (ui/PANEL.md); a schema carrying the English would put
the panel's voice in the dispatcher's mouth.

A `StrEnum` because the value crosses the bus: inside Python every call site
names a member and is type-checked, while on the wire a member is its own
name and a browser reads a plain string (ADR-0008).
"""

from enum import StrEnum

GENERATED = "ui/src/rejection.generated.ts"


class Reason(StrEnum):
    """Why the dispatcher refused a request outright rather than queuing it,
    in the order admission reaches them: the payload could not be read as a
    request at all, it names stock or track the railroad does not have, it
    departs from where the train is not standing, no arrival end survives
    pruning — none fits, or none can be entered — and, at the first launch
    attempt, no route to a surviving one exists."""

    MALFORMED = "malformed"
    UNKNOWN_TRAIN = "unknown_train"
    UNKNOWN_BLOCK = "unknown_block"
    WRONG_ORIGIN = "wrong_origin"
    NO_FIT = "no_fit"
    NO_ENTRY = "no_entry"
    UNREACHABLE = "unreachable"
