import { describe, expect, it } from "vitest";

import { BLOCK, LABEL, fitted } from "../src/render/units.js";

/** What a block's label has to fit inside: the rectangle's long side, which is
 *  the width whichever way the block stands, the label turning with it. */
const BODY = BLOCK.body.w;

describe("fitting a label to a block", () => {
  it("draws a name that fits at the full size", () => {
    // Every block id in the repo is this short or shorter, so the shrink is a
    // safety net rather than the usual case.
    for (const name of ["C4", "CE1", "airolo_1", "line_yellow"]) {
      expect(fitted(name, BODY)).toBe(LABEL.size);
    }
  });

  it("shrinks a name that would overrun, and only as far as it must", () => {
    const long = "x".repeat(40);
    const size = fitted(long, BODY);
    expect(size).toBeLessThan(LABEL.size);
    expect(long.length * LABEL.advance * size).toBeCloseTo(BODY);
  });

  it("never grows a short name to fill the rectangle", () => {
    expect(fitted("A", BODY)).toBe(LABEL.size);
    expect(fitted("", BODY)).toBe(LABEL.size);
  });

  it("shrinks monotonically, so a longer name is never drawn larger", () => {
    let last = Infinity;
    for (let length = 1; length <= 60; length++) {
      const size = fitted("x".repeat(length), BODY);
      expect(size).toBeLessThanOrEqual(last);
      last = size;
    }
  });
});
