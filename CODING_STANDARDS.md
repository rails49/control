# Coding standards

The review holds a change to these. Each is a judgement, not a count.

## One concern per file

A file, component or module holds one concern. Where it holds two or more
that could each stand on their own, split it: each part has its own inputs
and its own tests, and changes without the other. Each part must be big
enough to be worth a file; a two-line helper stays where it is used.
Length alone is no reason to split. A long table, a long list of cases or
one long algorithm is one concern.

A second concern shows as:

- a new kind or mode that shares little code with the ones already there;
- a block of the file with its own state or its own tests;
- a change that edits one part of the file for a reason the rest does not
  share.

## A piece any UI could use goes to look

A UI piece that reads no bus, no store and no control word, such as a
dialog that shows a text, is a look element
([org ADR-0016](https://github.com/rails49/.github/blob/main/docs/adr/0016-the-chrome-comes-from-look.md)).
It is filed in rails49/look, and the control change uses the release that
has it. `look-text-dialog` (rails49/look#60) was first built inside
`tc-timetable-dialog` (#1382).

## Lit

A list's rows are drawn by the list, or by a render module it calls, not
by one component per row. A shadow root per row breaks the columns'
alignment across rows unless the rows use CSS subgrid.
