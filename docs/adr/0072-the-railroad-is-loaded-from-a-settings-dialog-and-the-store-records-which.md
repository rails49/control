# The railroad is loaded from a settings dialog, and the store records which

The decision is [#733](https://github.com/rails49/control/issues/733). Amends
[ADR-0038](0038-the-ui-is-one-app-with-views-of-one-railroad.md) (the band
carries the means of loading another railroad),
[ADR-0060](0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)
(a railroad named on a command line is where an app starts),
[ADR-0064](0064-the-chrome-is-a-band-and-a-rail.md) (what the band carries)
and [ADR-0071](0071-a-rebuild-under-the-same-name-keeps-the-placements.md)
decision 5 (Save As names nothing). The org side is
[rails49/.github ADR-0014](https://github.com/rails49/.github/blob/main/docs/adr/0014-one-place-chooses-the-loaded-railroad-and-the-dcc-ex-ui-names-it.md).

A store holds several railroads, and four things choose among them:

- the band's picker, which loads one;
- the editor's New and Save As, which leave the editor and the stock view on
  a drawing that is not loaded, while the band names that drawing;
- `TC49_RAILROAD`, which the apps start on after every reboot, whatever a
  person loaded last;
- the dcc-ex script view, which edits the script of any railroad.

On the steel the railroad last loaded is the one the rails were built to. A
box that comes back on another one, or a page that names a drawing nobody is
running, shows a plan that does not match the track.

## Decision

1. **A gear on the band opens a Settings dialog.** It holds what belongs to
   all of control rather than to one railroad: loading a railroad, New
   railroad, Copy loaded railroad as…, and backup and restore. Further options
   of that kind go there; an option of one railroad goes in that railroad's
   view. It is a dialog and not a view, because a view shows or edits the
   loaded railroad (org ADR-0001).
2. **The band's left names the loaded railroad**, as
   `tc49/layout/state/railroad` reports it, and is not pressed. The picker
   goes.
3. **Every view holds the loaded railroad and no other.** The editor loses
   New and Save As. Making a railroad is the dialog's: New writes an empty
   drawing and loads it; Copy writes every document of the loaded railroad —
   drawing, roster, scenarios, script — under the new name and loads it.
4. **Load, New and Copy need track power `off`**, as loading does under
   ADR-0060, and no unsaved edits in the editor, as ON does under ADR-0071.
   Refused, New and Copy write nothing.
5. **The store records which railroad is loaded.** The layout binding writes
   it each time it is built on one and starts on it. `TC49_RAILROAD` and
   `--railroad` go. A restore leaves the record as it is, as it leaves the
   backup switch, and a load since the last backup does not refuse one.
6. **A binding with no railroad says so.** It publishes `""` on
   `tc49/layout/state/railroad`, so a page can tell "nothing loaded" from
   "layout not running", and the dialog loads or creates the first railroad
   on a new box.

## Consequences

- A new box comes up with no railroad. Its first one is loaded or created in
  the dialog; nothing names one at deploy time.
- Drawing a new station plan for a layout wired to steel means turning power
  off first. Loading it needed that already.
- A copied script may name blocks the new drawing lacks. That shows when the
  railroad is loaded, as after any edit to a drawing.
- Deleting and renaming a railroad are not in the dialog yet.
- Contract: [#727](https://github.com/rails49/control/issues/727) (`""` on
  the railroad row), [#728](https://github.com/rails49/control/issues/728)
  (the record), [#729](https://github.com/rails49/control/issues/729) (copy).
  Work: [#730](https://github.com/rails49/control/issues/730) (layout),
  [#731](https://github.com/rails49/control/issues/731) (deploy),
  [#732](https://github.com/rails49/control/issues/732) (band),
  [#733](https://github.com/rails49/control/issues/733) (dialog),
  [#734](https://github.com/rails49/control/issues/734) (editor).

## Considered

- **A view on the rail.** A full pane, at the cost of amending org ADR-0001,
  and settings in a different spot from occupancy's gear.
- **Naming it "Installation".** The org's installation is the box, its name,
  its certificate, its door and its page, and holds no store (org ADR-0009).
- **Keep `TC49_RAILROAD` as where a box starts.** A box would come back on a
  railroad other than the one built.
- **Start with nothing loaded after every reboot.** A person would load the
  same railroad by hand each time the box restarts.
- **Copy only the drawing, as Save As did.** The copy has no stock and no
  script, so on steel nothing can be placed or driven until both are rebuilt
  by hand.
