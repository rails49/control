# Generating the validation rules and the closed sets into TypeScript

`tc49 generate` writes two files — `ui/src/symbols.generated.ts` from
`store/symbols.py` and `ui/src/rejection.generated.ts` from `lib/rejection.py`
— and it stays at two. The name rule, the length rule and the stock closed
sets stay hand-written in TypeScript.

This is not a rejection of ADR-0014, which says field-level payload schemas are
generated into each language rather than written twice. It is a judgement about
which things are payload schemas.

## Why this is out of scope

The generator costs more than the duplication it removes. To keep two
characters and one bound in step across the language line it wants a Python
constants module, a renderer, an entry in `GENERATORS`, a committed generated
file, a staleness test, and an import on the far side. The rules themselves are
one line each:

```python
# src/tc49/lib/layout.py
def check_name(name: Any, what: str) -> None:
    if not isinstance(name, str) or not name or "." in name or "/" in name:
        raise ValueError(...)

def check_length(length: Any, where: str) -> int:
    if not isinstance(length, int) or length <= 0:
        raise ValueError(...)
```

Neither has changed since it was written. Weighed against a generator that has
to be maintained, read and kept green, having one copy in each language and a
test on each side is the smaller thing to own.

The same goes for `KINDS`, `MIXED`, `LIGHT_ENGINE` and `ORIENTATIONS` in
`lib/roster.py`: four strings, two strings and two more. `rejection.py` is
generated and is also a closed set, which looks like an inconsistency and is
not — a rejection reason is a value the store puts on the wire that the browser
must recognise one by one, so the set is a wire contract. A model's kind is
vocabulary, and adding one to it is a change to the roster document that will
be felt in both languages anyway.

What actually drove the request was four copies of the name rule and three of
the length rule, one of which was missing. Three of the four copies were
*inside TypeScript* — the browser was disagreeing with itself, not with Python.
That is fixed by having one copy, which is a net deletion and no machinery
(#500).

## What stays open

Generating the **document types and the review shapes** is a different
question and is not rejected here. It is also not free, because Python has no
description of its own documents to generate from: `Drawing.derive()` and
`Drawing.review()` in `store/drawing.py` build `dict[str, Any]` literals by
hand, and ADR-0014 says as much — "Python types nothing at the boundary
today". Giving Python that description and rebuilding the store's emit paths on
it is the cost ADR-0014 called in, and it is a project rather than a cleanup.
Nothing is blocked on it today. If it is taken up, it wants its own grilling
and its own ADR, and this file does not stand in its way.

## Prior requests

- #490: "ui: the model retypes rules and shapes that ADR-0014 says to generate"
