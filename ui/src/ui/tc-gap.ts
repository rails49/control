/**
 * A gap a person drags between two parts of the run view (ui/PANEL.md,
 * [#1344](https://github.com/rails49/control/issues/1344),
 * [#1391](https://github.com/rails49/control/issues/1391)).
 *
 * It takes the press and the drag, and while dragged it raises `gap-moved`
 * with the pointer's client point. It knows nothing of sizes: the view that
 * holds it works out what the point means and sizes the parts either side.
 *
 * `axis` is the way it is dragged: `x` for a gap between a left and a right
 * part, `y` for one between a top and a bottom part. A gap turned the other
 * way, as a turned page does, ends a drag. `dragging` is on the element from
 * the press to the release.
 */

import { LitElement, html, type PropertyValues } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { Point } from "../model/geometry.js";
import { gapStyles } from "./tc-gap.styles.js";

@customElement("tc-gap")
export class TcGap extends LitElement {
  static override styles = gapStyles;

  @property({ reflect: true }) axis: "x" | "y" = "x";

  /** Whether the gap is being dragged, on its element for its stylesheet. */
  @property({ type: Boolean, reflect: true }) dragging = false;

  constructor() {
    super();
    this.addEventListener("pointerdown", (event) => this.grab(event));
    this.addEventListener("pointermove", (event) => this.move(event));
    this.addEventListener("pointerup", () => this.release());
    this.addEventListener("pointercancel", () => this.release());
  }

  override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("axis")) this.release();
  }

  /** What takes the press: wider than the gap (`tc-gap.styles.ts`). */
  override render() {
    return html`<div></div>`;
  }

  private grab(event: PointerEvent): void {
    if (event.button !== 0) return;
    event.preventDefault();
    this.setPointerCapture?.(event.pointerId);
    this.dragging = true;
  }

  private move(event: PointerEvent): void {
    if (!this.dragging) return;
    const at: Point = { x: event.clientX, y: event.clientY };
    this.dispatchEvent(new CustomEvent<Point>("gap-moved", { detail: at }));
  }

  private release(): void {
    this.dragging = false;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-gap": TcGap;
  }
}
