/**
 * When the settings dialog's railroad part is refused, and why (#733, #737,
 * [ADR-0072](../../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).
 *
 * Loading another railroad rebuilds the rails a train stands on, so it waits
 * for track power `off`, as it does under ADR-0060; and it throws away what
 * the page holds of the railroad being left, so it waits for unsaved edits to
 * be saved, as ON does under ADR-0071. A page that has not heard which
 * railroad is loaded has no binding on the other end to ask. New and Copy
 * loaded as… end in a load of what they wrote, so they wait on the same
 * (ADR-0072, decision 4), and Copy on a railroad being loaded to copy.
 *
 * Turning the box off (#745) waits on the track being dead, as a load does:
 * a loco left on its last speed with nothing to stop it is what it would
 * strand.
 *
 * Pure functions in `model/` with a test, as the enablement rules beside them
 * are (EDITOR.md#tests): the dialog draws what these say and decides nothing.
 */

import type { Power } from "./trace.js";

/**
 * Why the railroad part is refused, `null` where it is not. The first that
 * holds is the reason:
 *
 * - `loaded` is `null`: the layout has not said which railroad is loaded, so
 *   no binding is there to answer a press;
 * - a railroad is loaded and the track has power — on or stopped — or has
 *   not said: the rails would change under a train;
 * - something is unsaved: the load would discard it.
 *
 * `loaded` is the layout's row as `RunStatus.railroad` has it — `null` not
 * heard, `""` none loaded (#727). With none loaded there are no rails built
 * to change under anything, so power is not asked: a binding with nothing
 * loaded reads no supply, and the first railroad on a new box is loaded from
 * here. `unsaved` is what `tc-app.losing` names — `"the drawing"`,
 * `"the roster"` or both — and `null` while nothing is.
 */
export function refusal(
  loaded: string | null,
  power: Power | null,
  unsaved: string | null,
): string | null {
  if (loaded === null) return "the layout has not said which railroad is loaded";
  if (loaded !== "" && power !== "off") {
    return "the track has power: switch it off to load another railroad";
  }
  if (unsaved !== null) return `${unsaved} has unsaved edits — save first`;
  return null;
}

/**
 * Why Copy loaded as… is refused, `null` where it is not: everything
 * `refusal` holds, and then a row naming `""` — nothing is loaded, so there
 * is nothing to copy. The first railroad on a new box is New's, not Copy's.
 */
export function copyRefusal(
  loaded: string | null,
  power: Power | null,
  unsaved: string | null,
): string | null {
  const refused = refusal(loaded, power, unsaved);
  if (refused !== null) return refused;
  if (loaded === "") return "no railroad is loaded to copy";
  return null;
}

/**
 * Why turning the box off is refused, `null` where it is not: the track has
 * power — on, or stopped, which is a live track under a stop — or the layout
 * has not said, which is never read as off. It takes neither the loaded
 * railroad nor what is unsaved: a box with nothing loaded still has a command
 * station, and the box going loses no edit a reload would not.
 */
export function boxRefusal(power: Power | null): string | null {
  if (power === null) return "the layout has not said whether the track has power";
  if (power !== "off") {
    return "the track has power: switch it off before turning the box off";
  }
  return null;
}
