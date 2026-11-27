/**
 * The dot in a train's colour: before a train's name in the run view's roster
 * and request list (#1410) and on a stock card, and beside each name in the
 * stock view's Colour field (#1411). The colour is set on the dot by
 * `trainStyle`, and the stylesheet's one `.dot` rule paints it
 * (`shared.styles.ts`). `slot` places it in a Shoelace control's slot.
 */

import { html, nothing, type TemplateResult } from "lit";

import type { TrainColour } from "../colour.generated.js";
import { trainStyle } from "../render/units.js";

export function dot(colour: TrainColour | undefined, slot?: string): TemplateResult {
  return html`<span class="dot" slot=${slot ?? nothing} style=${trainStyle(colour)}></span>`;
}
