import { describe, expect, it } from "vitest";

import type { SymbolSpec } from "../src/model/drawing.js";
import {
  ANCHORS,
  anchorOf,
  snapped,
  transformOf,
} from "../src/model/geometry.js";

/** Apply an SVG transform list the way SVG does: leftmost outermost, so the
 *  rightmost operation reaches the point first. */
function apply(transform: string, x: number, y: number): [number, number] {
  const steps = [...transform.matchAll(/(\w+)\(([^)]*)\)/g)].reverse();
  for (const [, op, args] of steps) {
    const n = args!.trim().split(/[\s,]+/).map(Number);
    if (op === "translate") [x, y] = [x + n[0]!, y + (n[1] ?? 0)];
    else if (op === "scale") [x, y] = [x * n[0]!, y * (n[1] ?? n[0]!)];
    else if (op === "rotate") {
      const a = (n[0]! * Math.PI) / 180;
      [x, y] = [x * Math.cos(a) - y * Math.sin(a), x * Math.sin(a) + y * Math.cos(a)];
    }
  }
  return [x, y];
}

describe("the artwork transform", () => {
  it("puts a leg exactly where the pin is, for every placement", () => {
    // The artwork is drawn in the symbol's own coordinates and the pins are
    // worked out separately. If the two ever disagree, a wire meets a symbol
    // beside its leg and the picture lies about what is joined.
    for (const kind of [
      "block",
      "terminal",
      "portal",
      "pin",
      "turnout",
      "crossing",
      "crossing_90",
      "crossing_90d",
      "single_slip",
      "double_slip",
    ] as const) {
      for (const rot of [0, 90, 180, 270] as const) {
        for (const flip of [false, true]) {
          const spec: SymbolSpec = { kind, at: [3, 2], rot, flip };
          const transform = transformOf(spec);
          for (const [pin, local] of Object.entries(ANCHORS[kind])) {
            const [x, y] = apply(transform, local.x, local.y);
            const anchor = anchorOf(spec, pin);
            expect(x).toBeCloseTo(anchor.x, 9);
            expect(y).toBeCloseTo(anchor.y, 9);
          }
        }
      }
    }
  });
});

describe("the 15 degree snap", () => {
  it("pulls a nearly level wireline level", () => {
    const to = snapped({ x: 0, y: 0 }, { x: 4, y: 0.1 });
    expect(to.y).toBeCloseTo(0, 9);
  });

  it("keeps the length the pointer gave it", () => {
    const to = snapped({ x: 1, y: 1 }, { x: 4, y: 3 });
    expect(Math.hypot(to.x - 1, to.y - 1)).toBeCloseTo(Math.hypot(3, 2), 9);
  });

  it("only ever lands on a multiple of 15 degrees", () => {
    for (const [x, y] of [
      [3, 1],
      [-2, 5],
      [0.5, -7],
    ]) {
      const to = snapped({ x: 0, y: 0 }, { x: x!, y: y! });
      const degrees = (Math.atan2(to.y, to.x) * 180) / Math.PI;
      expect(Math.abs(degrees / 15 - Math.round(degrees / 15))).toBeLessThan(1e-9);
    }
  });
});
