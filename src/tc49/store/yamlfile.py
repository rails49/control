"""Writing a YAML document back without disturbing what is already there.

Comments are most of what a hand-written drawing says — 90 of
`reversing-loops`'s 235 lines, including the junction-by-junction account of
the railroad and which decoder addresses are ganged — and the first editor save
writes a placement onto every symbol line.
A fresh dump would delete the lot, so ``save`` merges the incoming document
into the file key by key instead (ADR-0018, DRAWING.md).

An unchanged document comes back byte for byte. What does not survive is a
comment inside a sequence, a list being replaced whole for want of keys to
merge by, and the order of a mapping: an existing key keeps its place and a
new one joins at the end, which is what keeps a moved symbol out of the diff.

``ruamel.yaml`` ships no type information, which is why it is reached only
here and behind ``_comments``.
"""

from io import StringIO
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken


def _round_trip() -> YAML:
    """A ruamel instance, one per read or write.

    Sharing one was fine while callers are one at a time, but a dump that
    raises leaves it mid-document: ``dump_all`` clears the context manager it
    set up only on the way out, so the *next* dump writes into the failed
    dump's stream and leaves its own empty — a file truncated to nothing by a
    save that reported success. An instance per call has no state to leave
    behind, and a handful of files a session cannot notice the cost.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # never rewrap a line that was already written
    yaml.indent(mapping=2, sequence=4, offset=2)  # as the drawings are written
    return yaml


def save(path: Path, doc: dict[str, Any]) -> None:
    """Write `doc` to `path`, keeping everything the file says about itself.

    Serialised in full before the file is touched. Dumping into an open handle
    would truncate first, so a document that fails to serialise would leave
    nothing behind — and what it would have left nothing of is the only copy
    of the reasoning.
    """
    tree: Any = None
    if path.exists():
        with path.open() as f:
            tree = _round_trip().load(f)  # pyright: ignore[reportUnknownMemberType]
    out = StringIO()
    _round_trip().dump(  # pyright: ignore[reportUnknownMemberType]
        _merge(tree, doc), out
    )
    path.write_text(out.getvalue())


def _merge(into: Any, doc: Any) -> Any:
    """`doc`'s content laid onto `into`, so that everything unchanged keeps the
    node it was read into. Mappings merge by key; anything else replaces."""
    if into == doc:
        # Unchanged, so keep the node that was read: its comments, its blank
        # lines, and how its author chose to wrap it.
        return into
    if not isinstance(into, dict) or not isinstance(doc, dict):
        return _styled(doc)

    kept = cast(dict[str, Any], into)
    incoming = cast(dict[str, Any], doc)
    for gone in [key for key in kept if key not in incoming]:
        # The comment describing a symbol goes when the symbol goes, ruamel
        # holding a block comment against the key it precedes.
        del kept[gone]
    for key in incoming:
        if key in kept:
            kept[key] = _merge(kept[key], incoming[key])

    fresh = [key for key in incoming if key not in kept]
    if fresh:
        trailing = _detach_trailing(into)
        for key in fresh:
            kept[key] = _styled(incoming[key])
        if trailing is not None:
            _comments(into).setdefault(fresh[-1], [None] * 4)[2] = trailing
    return kept


def _detach_trailing(kept: Any) -> Any:
    """The comment block that follows a mapping, taken off its last key.

    ruamel hangs everything after a key's value on that key, so the paragraph
    introducing the *next* symbol belongs to the last key of the previous one.
    Appending without moving it first writes the new key underneath that
    paragraph, which still parses and reads as nonsense.
    """
    slot = _trailing_slot(kept)
    if slot is None:
        return None
    holder, key, index = slot
    token: Any = _comments(holder)[key][index]

    whole = str(token.value)
    eol, newline, block = whole.partition("\n")
    if not block:
        return None
    if eol.strip():
        # An end-of-line note belongs to the key it sits on, so only what
        # follows that line moves, behind the newline ending the new key's.
        token.value = eol + newline
        return CommentToken("\n" + block, CommentMark(0))
    _comments(holder)[key][index] = None
    return CommentToken(whole, CommentMark(0))


def _trailing_slot(node: Any) -> tuple[Any, Any, int] | None:
    """Where ruamel parks whatever follows a collection.

    A mapping holds it against its last key, a block sequence against its last
    item, and in a different slot each time. Where the last value is itself a
    collection the comment goes to *that* one, so a symbol ending in a block
    list of pins keeps the next symbol's paragraph one level down. The
    innermost holder wins, being the one physically nearest the text.
    """
    candidates: list[tuple[Any, Any, int]] = []
    while True:
        if isinstance(node, CommentedMap) and node:
            key = next(reversed(cast(dict[str, Any], node)))
            candidates.append((node, key, 2))
            node = cast(dict[str, Any], node)[key]
        elif isinstance(node, CommentedSeq) and node:
            items = cast(list[Any], node)
            candidates.append((node, len(items) - 1, 0))
            node = items[-1]
        else:
            break
    for holder, key, index in reversed(candidates):
        if _comments(holder).get(key, [None] * 4)[index] is not None:
            return holder, key, index
    return None


def _comments(node: Any) -> Any:
    """A node's per-key comment table."""
    return node.ca.items  # pyright: ignore[reportUnknownMemberType]


def _styled(value: Any) -> Any:
    """Plain data restyled the way these files are written by hand.

    A node read from the file carries its own style, but one the editor sends
    is plain Python and would otherwise come out as a block sequence: `at:`
    sprawled over three lines, every wire written `- - pin`. A sequence of
    scalars goes on one line; a mapping does too unless it nests one.
    """
    if isinstance(value, list):
        items = [_styled(item) for item in cast(list[Any], value)]
        seq = CommentedSeq(items)
        if all(not isinstance(item, (list, dict)) for item in items):
            _flow(seq)
        return seq
    if isinstance(value, dict):
        pairs = {key: _styled(v) for key, v in cast(dict[str, Any], value).items()}
        mapping = CommentedMap(pairs)
        if all(not isinstance(v, dict) for v in pairs.values()):
            _flow(mapping)
        return mapping
    return value


def _flow(node: Any) -> None:
    node.fa.set_flow_style()  # pyright: ignore[reportUnknownMemberType]
