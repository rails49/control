"""Why a request was rejected: one set, both sides answering to it (#126).

The dispatcher is the only app that mints a rejection reason, and every
reader of one — the panel first — has to know the same names. Minted as bare
literals at each call site, the set was something nobody held: #107 landed a
reason the panel could not spell, and nothing failed. So the names live here,
where the dispatcher takes them from and the UI's copy is generated from
(`rejection.generated.ts`, written by `tc49 generate`) rather than kept by
hand, the way the symbol library already is (ADR-0014).

The names alone. What a rejection *tells a reader* is wording, and wording
belongs to the panel (ui/PANEL.md); a schema carrying the English would put
the panel's voice in the dispatcher's mouth.

A `StrEnum` because the value crosses the bus: inside Python every call site
names a member and is type-checked, while on the wire a member is its own
name and a browser reads a plain string (ADR-0008).
"""

from enum import StrEnum

GENERATED_PATH = "ui/src/rejection.generated.ts"


class Reason(StrEnum):
    """Why the dispatcher rejected a request outright rather than queuing it,
    in the order admission reaches them: the payload could not be read as a
    request at all, it names stock or track the railroad does not have, it
    names a train that is known but off the layout, it departs from where the
    train is not standing, no arrival end survives pruning — none fits, none
    can be entered, or no route to one exists from the origin, which for a
    request queued behind a pending one is settled at the first launch attempt
    instead. A grant refused mid-run is a different event with its own reasons
    (`grant_refused`)."""

    MALFORMED = "malformed"
    UNKNOWN_TRAIN = "unknown_train"
    UNKNOWN_BLOCK = "unknown_block"
    NO_ORIGIN = "no_origin"
    WRONG_ORIGIN = "wrong_origin"
    NO_FIT = "no_fit"
    NO_ENTRY = "no_entry"
    UNREACHABLE = "unreachable"


_HEADER = """\
// Generated from src/tc49/lib/rejection.py. Run `tc49 generate` to update.
//
// Why the dispatcher rejected a request. The names alone: what each one
// tells a reader is the panel's wording, and no part of the schema.
"""


def render() -> str:
    """The whole of `ui/src/rejection.generated.ts`."""
    names = "\n".join(f'  | "{reason}"' for reason in Reason)
    return f"""\
{_HEADER}
/** A rejection reason, as `tc49/dispatch/request_rejected` carries it. A
 *  wording table keyed by this is total, so a reason minted in Python and
 *  left unworded here is a compile error rather than a raw token on screen. */
export type Reason =
{names};
"""
