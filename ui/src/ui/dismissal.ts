/**
 * The overlay a menu drops over the page, as behaviour.
 *
 * `shared.styles.ts` holds the one rule set — fixed, over the whole viewport,
 * under the menu itself — and this holds the element that wears it, for the
 * same three components. A press outside the menu lands here and dismisses
 * it, and nothing under it is clicked by the same press. That is what the
 * overlay is for, and it is why it cannot simply be let through.
 */

import { html, type TemplateResult } from "lit";

/** The overlay, with what a press outside the menu does. Rendered by the
 *  component the menu belongs to, so that the press is dismissed by the thing
 *  that knows what *dismissed* means there. */
export function dismissal(dismiss: () => void): TemplateResult {
  return html`<div class="dismiss" @pointerdown=${dismiss}></div>`;
}
