# The editor saves when it is left, and a railroad can be named without being built

The decision is [#887](https://github.com/rails49/control/issues/887). Amends
[ADR-0071](0071-a-rebuild-under-the-same-name-keeps-the-placements.md)
decisions 5 and 6 and
[ADR-0072](0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)
decisions 3 and 4.

The editor had a Save button, and ON was refused while the drawing had unsaved
edits. A saved drawing that is not a **valid drawing** left the apps on the
last build: ON was still allowed (#886), and after a restart the railroad
could not be reopened to fix it (#885). Picking an invalid railroad in
settings did nothing a person could see. Load, Restore and turning the box off
were refused while the track had power, with a line telling the person to
switch it off.

On the steel, an invalid drawing is usually a track plan being rebuilt. The
last build no longer matches the rails, so no train should run on it until the
drawing is valid again.

## Decision

1. **The editor saves when it is left**: on leaving the Edit view, when the
   page is hidden, before ON, and before a railroad is picked. There is no
   Save button and no timer. It saves only with track power `off`. Edits on a
   page where power came on from elsewhere stay on that page, marked unsaved,
   until it is next left with power off.
2. **ON with unsaved edits saves first**, and power comes on once the apps
   have built what was saved. Amends ADR-0071 decision 6, which refused ON.
3. **The Edit view does not open while track power is `on` or `draining`.**
   Power coming on while it is open moves the page to the Run view. Amends
   ADR-0071 decision 5, which kept the editor open read-only.
4. **A railroad whose drawing is invalid stays named.** The layout interface
   records it in the store and publishes it on `tc49/layout/state/railroad`
   with `built: false`. An app that reads that row builds nothing and keeps
   what it holds, including the placements on the broker. The page opens the
   drawing in the editor, draws the Run view grey with no trains and no
   gestures, and refuses ON with "Fix the drawing first". This holds after a
   save, after a restart, and after a pick in settings. Amends ADR-0072
   decision 3: the editor holds the loaded railroad whether or not it is
   built.
5. **Load, Restore and turning the box off take the power off themselves.**
   Each drains, and acts once `tc49/layout/state/power` reads `off`. While it
   waits the dialog says so and offers the stop sign, since a drain has no
   time limit. The precondition is unchanged; the page meets it instead of
   refusing. Amends ADR-0072 decision 4.

## Consequences

- Leaving the editor rebuilds every app, which takes about a second with the
  power off. A backup commit follows each save.
- After an invalid save the apps still run the last build in memory (#883);
  after a restart they hold none. ON is refused in both cases, so no train
  runs on either.
- Picking an invalid railroad under another name leaves the apps on the old
  build. Once its drawing is valid they build it with nothing placed, as any
  load under another name does (ADR-0071 decision 2).
- `tc49/layout/state/railroad` gains `built`. rails49/dccex reads the row:
  its translator must build nothing on `built: false`.

## Considered

- **Save every minute as well.** It saves half-finished drawings often and
  adds nothing once leaving and hiding the page both save.
- **Keep work in progress in a draft beside the drawing.** It is a second copy
  of every drawing to keep in step, and ON must still wait for it.
- **Keep work in progress in the browser.** It is lost when the person picks
  up another device.
- **Refuse to save an invalid drawing.** The work is lost when the page
  closes.
- **Cut the power at once before Load, Restore or turning the box off.** A
  moving train stops wherever it is, possibly across a turnout.
