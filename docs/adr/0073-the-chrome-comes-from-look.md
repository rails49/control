# The chrome comes from look

The decision is [rails49/look#12](https://github.com/rails49/look/issues/12#issuecomment-6156396667),
and the work is [#749](https://github.com/rails49/control/issues/749).
Supersedes [ADR-0064](0064-the-chrome-is-a-band-and-a-rail.md). Amends
[ADR-0038](0038-the-ui-is-one-app-with-views-of-one-railroad.md) (the band
and the bar),
[ADR-0051](0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)
and
[ADR-0062](0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)
(ON, STOP and OFF), and
[ADR-0070](0070-the-simulator-obeys-the-bands-power-presses.md) (the band's
power presses).

rails49 has several UIs: control, occupancy, the dcc-ex UI, the landing page
and the installation page. Each drew its own band and rail. Control kept a
copy of the shared colours and sizes in `ui/look/`, pinned to the commit they
came from, and a test checked its own styles against them.
[`@rails49/look`](https://github.com/rails49/look) is one package that draws
the band, the rail, the dialogs and the Shoelace theme for all of them
([look#1](https://github.com/rails49/look/issues/1)). look#12 decided how
control's chrome maps onto it, and look v0.2.0 added what control needed.

## Decision

1. **Control's band, rail, track-power control, dialog shell, Shoelace theme
   and glyphs come from `@rails49/look`**, pinned to a release tag
   (`github:rails49/look#v0.2.0`). `tc-app` draws `look-shell`, `look-band`
   and `look-rail` and listens for `look-press`, `look-view` and
   `look-power`.
2. **Control styles none of it.** `scripts/check.sh` runs
   `look-check ui/src ui/index.html`, which fails on a selector naming a
   `look-` element, on setting one of look's tokens or a `--sl-*` property,
   and on `sl-*::part()` in app code. The gate also runs the vite build.
3. **The band.**
   - The loaded railroad's name is `look-about name=…`, or *no railroad
     loaded*. Unsaved edits are `detail="unsaved"`.
   - Each fault is a `look-chip` with its whole sentence as its `title`: the
     store or the broker not answering, *does not derive*, and what the
     hardware says is wrong with the supply. Every fault is the same red.
   - *drawing frozen* (editing view only) and the session clock are
     `look-reading`s.
   - The backup note is `look-band-press word=…` and opens the backup dialog.
   - The gear is `look-gear` and opens Settings.
4. **Track power is `look-power`**: one power toggle and a red stop sign. The
   toggle is green when on, dimmed when off and red when stopped.
   - **OFF still drains.** The toggle asking for `off` is the drain request
     of ADR-0062. While the drain is outstanding the toggle shows
     `state="draining"` and pulses green. Pressing it then asks for `on`,
     which abandons the drain. The stop sign stays live.
   - From stopped the toggle asks for `on`, so stopped to off takes two
     presses.
   - The control is dead with the reason *Waiting for the station* before the
     station has said where power stands, and while the broker is not
     answering.
   - It is dead with the reason *Save the railroad first* while the loaded
     railroad has unsaved edits and power is off (ADR-0071, decision 6).
   - `supply()` in `ui/src/model/commands.ts` decides what the control shows.
5. **The rail.**
   - The views are `look-view`s: run `stoplights`, throttle look's own
     `throttle`, stock `train-freight-front`, edit `pencil`. Pressing the
     current view does nothing.
   - The commands are `look-command`s in `look-group`s labelled View, File and
     Edit. Each key is in look's `Mod+S` form, shown for the platform in the
     tooltip.
   - Glyphs: save `floppy`, export `box-arrow-up`, undo
     `arrow-counterclockwise`, redo `arrow-clockwise`, zoom in and zoom out by
     name, fit `fullscreen`, netlist `layout-sidebar-reverse`, properties
     `sliders`, rotate look's own `rotate`, flip `symmetry-vertical`, delete
     `trash`. Each command and view names its glyph in `model/commands.ts`
     and `model/views.ts`.
   - HOLD/GO is a `look-command word=…` in a `look-group end` labelled Run, at
     the rail's far end.
   - Below a short window the rail lies along the top. That strip is look's.
6. **Glyphs are Bootstrap Icons, served from control's own origin.** Vite
   copies Shoelace's assets to `/shoelace`, and `main.ts` calls
   `setBasePath('/shoelace')`. Nothing is fetched from a CDN, so the editor
   still works on the railroad's own network.
7. **The work pane follows the operating system's dark mode**
   (`prefers-color-scheme`). `look.css` carries both Shoelace themes. The
   chrome has one value in both.
8. **All five dialogs are `look-dialog`**: Settings, Backup, Properties, the
   stock Photo dialog and New model. The header is on the band's blue and the
   footer is grey. A work-pane component with Shoelace widgets puts look's
   `lookTheme` first in its styles.

## What is deleted

`tc-header`, `tc-rail`, `ui/icons.ts`, `ui/theme.ts` and its test,
`ui/look/` (the copied `tokens.css` and its README) and the styles tests that
read it,
the palette's chrome entries (`--band`, `--band-ink`, `--rail`,
`--rail-group`, `--stop`, `--stop-ink`), and `RAIL_BUTTON_PX`, `RAIL_PAD_PX`
and `RAIL_TURNS_PX` in `render/units.ts`. Also gone: the dot that marked
unsaved edits, the two weights of red on the band, control's own switching of
the Shoelace theme, and the Properties dialog's red field border and help text,
which set `--sl-input-*`.

## Consequences

- ADR-0064's division of the chrome into a band and a rail stands. Its clause
  that the glyphs are drawn in `ui/icons.ts` and not fetched is replaced by
  decision 6.
- Where ADR-0038, 0051, 0062 and 0070 say ON, STOP and OFF, read the power
  toggle asking for `on`, the stop sign, and the toggle asking for `off`. The
  bus gestures behind them are unchanged.
- A change to the chrome is a change in look and a new release. Control takes
  it by moving the tag, and look's release workflow opens that pull request.
- The suites draw no glyphs. `ui/test/setup.ts` registers an icon resolver
  that returns nothing, so Shoelace fetches nothing under test.
