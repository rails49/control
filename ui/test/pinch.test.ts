/**
 * Two fingers zoom and pan the canvas (#894, model/pinch.ts): numbers in,
 * numbers out. Every point is in the squares of the view the pinch began in.
 */

import { describe, expect, it } from "vitest";

import type { Point } from "../src/model/geometry.js";
import { pinched, type Pair } from "../src/model/pinch.js";
import type { Box } from "../src/model/scene.js";

const VIEW: Box = { x: 0, y: 0, w: 16, h: 10 };

/** Where a square of the drawing sits in the view, as a fraction across and
 *  down — what a finger resting on it sees. */
function seen(view: Box, square: Point): Point {
  return { x: (square.x - view.x) / view.w, y: (square.y - view.y) / view.h };
}

function closeTo(actual: Point, expected: Point): void {
  expect(actual.x).toBeCloseTo(expected.x);
  expect(actual.y).toBeCloseTo(expected.y);
}

describe("pinched", () => {
  it("leaves the view alone while the fingers are still", () => {
    const at: Pair = [{ x: 2, y: 3 }, { x: 6, y: 5 }];
    expect(pinched(VIEW, at, at)).toEqual(VIEW);
  });

  it("pans with two fingers moving together", () => {
    const from: Pair = [{ x: 2, y: 3 }, { x: 6, y: 5 }];
    const to: Pair = [{ x: 3, y: 1 }, { x: 7, y: 3 }];
    // The drawing follows the fingers: one square right and two up, so the
    // view moves one square left and two down.
    expect(pinched(VIEW, from, to)).toEqual({ x: -1, y: 2, w: 16, h: 10 });
  });

  it("zooms in about the midpoint as the fingers spread", () => {
    const from: Pair = [{ x: 6, y: 5 }, { x: 10, y: 5 }];
    const to: Pair = [{ x: 4, y: 5 }, { x: 12, y: 5 }];
    const view = pinched(VIEW, from, to);
    expect(view.w).toBeCloseTo(8);
    expect(view.h).toBeCloseTo(5);
    // The midpoint (8, 5) stays where it was on the screen.
    closeTo(seen(view, { x: 8, y: 5 }), seen(VIEW, { x: 8, y: 5 }));
  });

  it("keeps each finger on the square it landed on", () => {
    const from: Pair = [{ x: 2, y: 2 }, { x: 4, y: 4 }];
    const to: Pair = [{ x: 5, y: 1 }, { x: 13, y: 9 }];
    const view = pinched(VIEW, from, to);
    closeTo(seen(view, from[0]), seen(VIEW, to[0]));
    closeTo(seen(view, from[1]), seen(VIEW, to[1]));
  });

  it("zooms out as the fingers close", () => {
    const from: Pair = [{ x: 4, y: 5 }, { x: 12, y: 5 }];
    const to: Pair = [{ x: 6, y: 5 }, { x: 10, y: 5 }];
    expect(pinched(VIEW, from, to).w).toBeCloseTo(32);
  });

  it("only pans when the fingers meet", () => {
    const from: Pair = [{ x: 4, y: 5 }, { x: 12, y: 5 }];
    const to: Pair = [{ x: 9, y: 5 }, { x: 9, y: 5 }];
    expect(pinched(VIEW, from, to)).toEqual({ x: -1, y: 0, w: 16, h: 10 });
  });
});
