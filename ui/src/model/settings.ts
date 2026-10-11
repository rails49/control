/**
 * When the settings dialog's railroad part is refused, and why (#733,
 * [ADR-0072](../../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).
 *
 * Loading another railroad rebuilds the rails a train stands on, so it waits
 * for track power `off`, as it does under ADR-0060; and it throws away what
 * the page holds of the railroad being left, so it waits for unsaved edits to
 * be saved, as ON does under ADR-0071. A page that has not heard which
 * railroad is loaded has no binding on the other end to ask.
 *
 * A pure function in `model/` with a test, as the enablement rules beside it
 * are (EDITOR.md#tests): the dialog draws what this says and decides nothing.
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
 * here. `unsaved` is what the app's discard question names — `"the drawing"`,
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
