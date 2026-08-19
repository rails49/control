import { describe, expect, it } from "vitest";

import type { SymbolSpec } from "../src/model/drawing.js";
import { ANCHORS, anchorOf, transformOf } from "../src/model/geometry.js";

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
