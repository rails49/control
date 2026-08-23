/**
 * The overlay a menu drops over the page, as behaviour.
 *
 * `shared.styles.ts` holds the one rule set — fixed, over the whole viewport,
 * under the menu itself — and this holds the element that wears it, for the
 * same three components. A press outside the menu lands here and dismisses
 * it, and nothing under it is clicked by the same press. That is what the
 * overlay is for, and it is why it cannot simply be let through.
 *
 * A right-click is the case that press-and-swallow gets wrong
 * ([#180](https://github.com/rails49/control/issues/180)). The overlay is the
 * topmost thing over the drawing while it is there, so the second right-click
 * landed on it, `contextmenu` never reached the canvas, nothing called
 * `preventDefault`, and Chrome's own menu opened over the railroad with no
 * menu of ours on the train that was clicked. So the overlay forwards it: the
 * menu comes down, and the press goes on to whatever is under the point,
 * which is what would have had it with no menu open.
 *
 * What comes of that is the drawing's answer and not this module's. The
 * forwarded event is dispatched cancellable and the original is prevented
 * only if it came back prevented, so the canvas suppresses the native menu
 * exactly as it does on the first right-click, and a press over the roster or
 * the pane keeps whatever it does with no menu open.
 */

import { html, type TemplateResult } from "lit";

/** The overlay, with what a press outside the menu does. Rendered by the
 *  component the menu belongs to, so that the press is dismissed by the thing
 *  that knows what *dismissed* means there. */
export function dismissal(dismiss: () => void): TemplateResult {
  return html`<div
    class="dismiss"
    @pointerdown=${dismiss}
    @contextmenu=${(event: MouseEvent) => dismissAndForward(event, dismiss)}
  ></div>`;
}

/**
 * The right-click the overlay is standing in the way of: the menu comes down,
 * the press is handed on to whatever is under the point, and the native menu
 * is answered for as whatever took it answered.
 *
 * The overlay is taken out of the hit test for the length of the hand-on and
 * put back at the end of it. **After** is what matters: every frame inside
 * `dispatchEvent` still sees every overlay the press has already passed as
 * inert, so it moves one overlay deeper each time and the walk terminates,
 * and by the time anything is put back the recursion has unwound. Restoring
 * before the dispatch is what had two overlays handing one press back and
 * forth until the stack gave out (`82f2abc`).
 *
 * Restoring at all is what the *next* menu's overlay needs. A forwarded
 * right-click dismisses one menu and opens another within a single task, lit
 * batches that into one update, and lit-html reuses the same `div.dismiss` —
 * so a mark left here is worn by a menu that is still up, whose overlay then
 * takes no press at all
 * ([#186](https://github.com/rails49/control/issues/186)).
 */
function dismissAndForward(event: MouseEvent, dismiss: () => void): void {
  dismiss();
  const overlay = event.currentTarget as HTMLElement;
  overlay.style.pointerEvents = "none";
  try {
    const under = deepestAt(event.clientX, event.clientY);
    if (under === null) return;
    const again = new MouseEvent("contextmenu", {
      bubbles: true,
      composed: true,
      cancelable: true,
      clientX: event.clientX,
      clientY: event.clientY,
      button: event.button,
    });
    under.dispatchEvent(again);
    if (again.defaultPrevented) event.preventDefault();
  } finally {
    overlay.style.pointerEvents = "";
  }
}

/**
 * The deepest element at the point, shadow roots and all: `elementFromPoint`
 * answers with the host of a shadow tree rather than with what is inside it,
 * so each root it names is asked the same question again. The canvas draws
 * inside two of them, and dispatching at the host would never reach the
 * surface that handles the press.
 *
 * A query. Which elements the hit test may answer with is arranged by the
 * caller above, for as long as it is asking.
 */
function deepestAt(x: number, y: number): Element | null {
  let found = document.elementFromPoint(x, y);
  for (;;) {
    const inside = found?.shadowRoot?.elementFromPoint(x, y) ?? null;
    if (inside === null || inside === found) return found;
    found = inside;
  }
}
