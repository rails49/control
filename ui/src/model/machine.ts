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
 *  gesture visuals, announce that the selection changed, or announce that the
 *  document changed. Nothing about the viewport is here — zoom, the wheel and
 *  the middle-button pan are the same in both views and so the canvas's own. */
export type Outcome = "quiet" | "render" | "picked" | "changed";

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

/** What a gesture in flight puts on the sheet, in grid squares rather than in
 *  markup: the model owns the document and a component owns the DOM
 *  (EDITOR.md#implementation). */
export interface Marks {
  /** The box a rubber band is being pulled out to. */
  band?: Span;
}

/**
 * What a press means, one call per pointer event.
 *
 * The canvas converts the pointer's pixels into squares, calls a method here,
 * and maps the `Outcome` onto rendering and events; it draws what `marks` and
 * `shift` say and decides no meaning of its own. Each view hands over the
 * machine that is its own — the editor's `Gesture`, the run view's `Drag` —
 * bound to the document it is about.
 */
export interface Machine {
  down(point: Point, input: Input): Outcome;
  moved(point: Point, screen: Point): Outcome;
  up(point: Point): Outcome;
  /** The pointer left the sheet, or the gesture under it was cancelled. */
  left(): Outcome;
  /** A right-click, and what it found for the view to build a menu about —
   *  `null` where the press meant something else and no menu opens. The canvas
   *  passes it on with where the pointer was and reads none of it. */
  menu(point: Point): { outcome: Outcome; found: object | null };
  /** How far a symbol is drawn from where the document puts it. */
  shift(name: string): Point;
  /** What the gesture in flight draws, `null` for none. */
  readonly marks: Marks | null;
}
