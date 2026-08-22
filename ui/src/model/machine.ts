/**
 * What the canvas asks of whatever decides what a press means.
 *
 * The canvas converts the pointer's pixels into squares and calls one method
 * per event; every rule after the conversion is the view's, in the machine it
 * hands over — `Gesture` for the editor (gesture.ts), `Drag` for the run view
 * (drag.ts). Both are driven the same way and neither is reached for here, so
 * the types are in a module of their own rather than in either machine's.
 */

import type { Point } from "./geometry.js";

/** What the caller has to do about a gesture event: nothing, redraw the
 *  gesture visuals, announce that the selection changed, announce that the
 *  document changed, or shift the view by a grid delta — the one effect a
 *  machine cannot apply itself, the viewBox being the component's. */
export type Outcome = "quiet" | "render" | "picked" | "changed" | { pan: Point };

/** What a pointer event says beyond where it is in squares: the button, the
 *  shift key, and the screen pixels — the only frame a slop threshold means
 *  anything in, a square being however many pixels the zoom makes it. */
export interface Input {
  button: number;
  shift: boolean;
  screen: Point;
}

/** Two points a gesture is stretched between, in grid squares. */
export interface Span {
  from: Point;
  to: Point;
}
