/**
 * The run view's pane, the roster with the request list: which side of the
 * drawing it is on, and the sizes a person dragged its two gaps to
 * (ui/PANEL.md, [#1344](https://github.com/rails49/control/issues/1344),
 * [#1390](https://github.com/rails49/control/issues/1390),
 * [#1391](https://github.com/rails49/control/issues/1391)).
 *
 * The pane is left of the drawing, or above it on a page taller than it is
 * wide. The gap between the pane and the drawing sets the pane's size,
 * measured from the view's edge on the pane's side: the left edge, or the
 * top one.
 *
 * The gap between the trains list and the timetable list sets the trains
 * list's size. With the pane on the left the lists are one above the other
 * and it is the trains list's height, from the view's top edge; with the
 * pane above they are side by side and it is the trains list's width, from
 * the view's left edge. The pane spans the view that way in either
 * arrangement. Until this gap is first dragged the stylesheet sizes the
 * lists: one above the other, the trains list as tall as its rows up to half
 * the pane; side by side, half and half.
 *
 * Each gap's size is kept in the browser's `localStorage` under its own key,
 * one for each arrangement. It is not on the bus and not in the store.
 */

import { GAP_PX } from "@rails49/look";

import type { Point } from "./geometry.js";

/** Where the pane is: left of the drawing, or above it on a page taller than
 *  it is wide. */
export type Arrangement = "left" | "above";

/** The two gaps a person drags: between the pane and the drawing, and
 *  between the trains list and the timetable list. */
export type Gap = "pane" | "lists";

/** The media query that is true of a page taller than it is wide. The run
 *  view's stylesheet lays the pane out by it and the view asks it which
 *  arrangement that is. */
export const UPRIGHT = "(orientation: portrait)";

/** The least size of the pane in CSS pixels, where the roster is still
 *  usable. */
export const LEAST = 144;

/** What the pane leaves the drawing, in CSS pixels: of the view's width with
 *  the pane on the left, of its height with the pane above. */
export const DRAWING: Record<Arrangement, number> = { left: 256, above: 192 };

/** The least size each of the two lists keeps, in CSS pixels: its height
 *  with the pane on the left, its width with the pane above. */
export const LIST: Record<Arrangement, number> = { left: 96, above: 144 };

/** The way a gap is dragged: `x` for a gap between a left and a right
 *  part, `y` for one between a top and a bottom part. */
export type Axis = "x" | "y";

/** The way a gap is dragged in an arrangement. The lists lie the other way
 *  from the pane and the drawing: one above the other with the pane on the
 *  left, side by side with the pane above. */
export function axisOf(gap: Gap, arrangement: Arrangement): Axis {
  return (gap === "pane") === (arrangement === "left") ? "x" : "y";
}

/**
 * The size in CSS pixels a gap at a client point sets, along its axis from
 * the view's left or top edge: the pane's, or the trains list's. The pane is
 * held to `LEAST` and to what `DRAWING` leaves of the view; each list is held
 * to `LIST`. In a view too small for both sides, the size's own least holds.
 */
export function sizeAt(gap: Gap, arrangement: Arrangement, view: DOMRect, at: Point): number {
  const [wanted, room] =
    axisOf(gap, arrangement) === "x"
      ? [at.x - view.left, view.width]
      : [at.y - view.top, view.height];
  const [least, beyond] =
    gap === "pane" ? [LEAST, DRAWING[arrangement]] : [LIST[arrangement], GAP_PX + LIST[arrangement]];
  return Math.round(Math.max(least, Math.min(wanted, room - beyond)));
}

function key(gap: Gap, arrangement: Arrangement): string {
  return `tc49.${gap}.${arrangement}`;
}

/** The size this browser keeps for a gap in an arrangement, `null` for
 *  none. */
export function kept(gap: Gap, arrangement: Arrangement): number | null {
  const size = localStorage.getItem(key(gap, arrangement));
  return size === null ? null : Number(size);
}

export function keep(gap: Gap, arrangement: Arrangement, size: number): void {
  localStorage.setItem(key(gap, arrangement), String(size));
}
