"""A small document that outlives the process that wrote it (#123).

Two callers, for two different reasons: the bus binding keeps the retained
values of every ``tc49/*/state/*`` topic, which is what an MQTT broker will
do for it later, and the simulator keeps the placement a real railroad keeps
in steel (ADR-0030). Neither is a store — there is no query, no history and
no schema, only the last picture — so the whole of it is written every time
and read back whole.
"""

import json
from pathlib import Path
from typing import Any, cast

Document = dict[str, Any]


def sibling(path: Path, tag: str) -> Path:
    """A second document beside the one that was named, tagged:
    `runs/today.json` and `reversing-loops` give `runs/today.reversing-loops.json`. A
    session is given one path and more than one document hangs off it: one
    state file per railroad, and the simulator's placement beside each."""
    return path.with_name(f"{path.stem}.{tag}{path.suffix}")


def read(path: Path) -> Document:
    """What the file holds, or nothing where there is no file yet — the first
    session of all names a path that does not exist."""
    return cast(Document, json.loads(path.read_text())) if path.exists() else {}


def write(path: Path, document: Document) -> None:
    """The whole document, to a temporary file in the target's own directory
    and renamed over it. Rename within a directory is atomic, so a process cut
    mid-write leaves the previous good copy in place and a partial file that
    nothing ever reads — `read` opens the target and no other name.

    The directory is made if it is not there. A session names where it wants
    its file kept and the first write is the one that has to make it, which
    is not error handling: `--state runs/today.json` is an ordinary thing to
    type, and it must not die after the banner has printed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document))
    temporary.replace(path)
