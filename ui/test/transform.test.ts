import { describe, expect, it } from "vitest";

import type { SymbolSpec } from "../src/model/drawing.js";
import {
  ANCHORS,
  anchorOf,
  gridPointOf,
  labelTurn,
  transformOf,
  uprightAt,
} from "../src/model/geometry.js";
import { BLOCK } from "../src/render/units.js";

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

  it("draws a block's A upright and at its A corner, for every placement", () => {
    // A plus looks the same however the block is turned; a letter does not.
    // Under a half turn drawn in the block's own frame it would stand on its
    // head (#922).
    for (const rot of [0, 90, 180, 270] as const) {
      for (const flip of [false, true]) {
        const spec: SymbolSpec = { kind: "block", at: [3, 2], rot, flip };
        const transform = `${transformOf(spec)} ${uprightAt(spec, BLOCK.endA)}`;
        const [x0, y0] = apply(transform, 0, 0);
        const corner = gridPointOf(spec, BLOCK.endA);
        expect(x0).toBeCloseTo(corner.x, 9);
        expect(y0).toBeCloseTo(corner.y, 9);
        const a = (labelTurn(spec) * Math.PI) / 180;
        for (const [dx, dy, ex, ey] of [
          [1, 0, Math.cos(a), Math.sin(a)],
          [0, 1, -Math.sin(a), Math.cos(a)],
        ] as const) {
          const [x, y] = apply(transform, dx, dy);
          expect(x - x0).toBeCloseTo(ex, 9);
          expect(y - y0).toBeCloseTo(ey, 9);
        }
      }
    }
  });
});
