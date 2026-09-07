# The chrome is a band and a rail

Amends "The band is the system; the bar is the document" in
[ADR-0038](0038-the-ui-is-one-app-with-views-of-one-railroad.md).

ADR-0038 divided the chrome into two rows by what each is about: a **band**
carrying what is true of the whole system, and a **bar** under it carrying menus
that act on the current view's document. The division is sound and this does not
touch it. What changes is where the second half sits.

## Why the row goes

The occupancy UI (`../occupancy`) runs the same stack — Lit, Shoelace, Vite —
against the same railroad, and puts every press in a column down the left of the
work pane with no menu row at all. Two apps a person moves between within one
session should not each teach a different place to look for the same kind of
control.

The row is also the wrong shape for what it carries. A menu bar earns its width
when a view has dozens of verbs; three of the four views here have **none** —
the throttle and the stock screen draw no document, and the run view has zoom
and fit — so the row is empty or nearly so most of the time while still taking a
band's worth of height off the canvas. The editor's eleven verbs are the whole
of what needs a home, and eleven icon buttons are a short column.

Height is what the work pane is short of. The band is horizontal and the drawing
is wide, so a second horizontal row costs the canvas exactly what it can least
spare, and a column costs it width it has more of.

## Decision

**The chrome is a band across the top and a rail down the left.** The band is
unchanged in what it is about — the whole system — and loses only the view
selector. The rail carries **what the current view offers**: the views
themselves, then that view's commands as icon buttons, then any press of its own.

`tc-menubar` is deleted. `MENUS` and `TOOLS` in `model/commands.ts` become one
`RAIL`, a per-view list of groups.

**The view selector moves to the rail's top group.** ADR-0038 made the views a
list rendered as a selector with the current one marked, and that is unchanged;
only the place it sits. It goes to the rail because the rail is where a person
presses things, and being on the band left it competing for the same end of the
row as track power.

**Zoom out, zoom in and fit are the rail's first command group in every view
that has one**, so the three buttons pressed constantly while drawing and while
following a train are in the same place whichever view is up (#168).

**Rotate, Flip, Delete and Properties are not on the rail.** They already read
in the editor's right-click menu with their keys beside them, and they apply to
a selection — a permanent column of four buttons that are dead whenever nothing
is selected says less than a menu that opens on the thing they act on.

## What this does not decide

The rail is not a Shoelace `sl-icon-button` column the way occupancy's is. The
glyphs here are drawn in `ui/icons.ts` rather than fetched, because the editor
has to work on the railroad's own network (EDITOR.md#implementation), and that
is unchanged.

## Consequences

- ADR-0038's sentence "The **bar** carries what acts on the current view's
  document: File, Edit, View, zoom, HOLD and GO" reads *the rail* and is
  otherwise intact. Its two-rows-of-chrome figure is a band and a rail.
- `tc-app` loses the `barMenu` state and the keyboard branch that served it: a
  rail has nothing that comes down over the work, so there is no state in which
  the keyboard belongs to the chrome.
- `menuShortcut` leaves `shared.styles.ts`. With the bar gone only `tc-menu`
  wears it, and nothing lives in that module that fewer than two sheets wear
  (#132).
- `tc-menu`, the right-click menu, is untouched. It is not the bar, and the four
  selection verbs it carries are now the only way to reach them by pointer.
- Below a short window height the rail turns into a horizontal strip, as
  occupancy's does: a column of fifteen buttons does not fit a phone held
  sideways, and the throttle is used that way.
