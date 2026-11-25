/**
 * The run view's pane, the roster with the request list: which side of the
 * drawing it is on, and the size a person dragged its divider to
 * (ui/PANEL.md, [#1344](https://github.com/rails49/control/issues/1344)).
 *
 * The size is kept in the browser's `localStorage`, one for each arrangement.
 * It is not on the bus and not in the store.
 */

import type { Point } from "./geometry.js";

/** Where the pane is: left of the drawing, or below it on a page taller than
 *  it is wide. */
export type Arrangement = "left" | "below";

/** The media query that is true of a page taller than it is wide. The run
 *  view's stylesheet lays the pane out by it and the view asks it which
 *  arrangement that is. */
export const UPRIGHT = "(orientation: portrait)";

/** The least size of the pane in CSS pixels, where the roster is still
 *  usable. */
export const LEAST = 144;

/** What the pane leaves the drawing, in CSS pixels: of the view's width with
 *  the pane on the left, of its height with the pane below. */
export const DRAWING: Record<Arrangement, number> = { left: 256, below: 192 };

/**
 * The pane's size in CSS pixels with the divider at a client point: its width
 * from the view's left edge, or its height from the view's bottom edge, held
 * to `LEAST` and to what `DRAWING` leaves of the view. In a view too small for
 * both, `LEAST` holds.
 */
export function sizeAt(arrangement: Arrangement, view: DOMRect, at: Point): number {
  const [wanted, room] =
    arrangement === "left"
      ? [at.x - view.left, view.width]
      : [view.bottom - at.y, view.height];
  return Math.round(Math.max(LEAST, Math.min(wanted, room - DRAWING[arrangement])));
}

function key(arrangement: Arrangement): string {
  return `tc49.pane.${arrangement}`;
}

/** The size this browser keeps for an arrangement, `null` for none. */
export function kept(arrangement: Arrangement): number | null {
  const size = localStorage.getItem(key(arrangement));
  return size === null ? null : Number(size);
}

export function keep(arrangement: Arrangement, size: number): void {
  localStorage.setItem(key(arrangement), String(size));
}
