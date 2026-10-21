/**
 * Two fingers on the canvas: where they are says what the view is (#894,
 * EDITOR.md#canvas).
 *
 * The grid square each finger landed on stays under that finger. Two fingers
 * moving together carry the drawing with them, and two fingers spreading or
 * closing zoom about their midpoint, by the ratio of how far apart they were
 * to how far apart they are. Pure arithmetic on squares, so it lives here and
 * the canvas only converts pixels.
 */

import type { Point } from "./geometry.js";
import type { Box } from "./scene.js";

/** The two fingers, in grid squares. */
export type Pair = readonly [Point, Point];

/** Closer than this, two fingers have no distance to scale by and the pinch
 *  only pans. */
const TOUCHING = 1e-6;

/**
 * The view that keeps the drawing under two fingers.
 *
 * `view` is the view when the second finger landed, `from` where the two
 * landed and `to` where they are now — both read in that same view's squares,
 * so the answer depends on nothing but the gesture so far and a pinch drawn
 * back to where it began is the view it began in.
 */
export function pinched(view: Box, from: Pair, to: Pair): Box {
  const was = Math.hypot(from[1].x - from[0].x, from[1].y - from[0].y);
  const now = Math.hypot(to[1].x - to[0].x, to[1].y - to[0].y);
  const scale = was < TOUCHING || now < TOUCHING ? 1 : was / now;
  const anchor = midpoint(from);
  const held = midpoint(to);
  return {
    x: anchor.x - (held.x - view.x) * scale,
    y: anchor.y - (held.y - view.y) * scale,
    w: view.w * scale,
    h: view.h * scale,
  };
}

function midpoint([a, b]: Pair): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}
