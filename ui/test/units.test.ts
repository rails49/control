import { describe, expect, it } from "vitest";

import { BLOCK, LABEL, PORTAL, fitted } from "../src/render/units.js";

/** What a block's label has to fit inside: the rectangle's long side, which is
 *  the width whichever way the block stands, the label turning with it. */
const BODY = BLOCK.body.w;

describe("fitting a label to a block", () => {
  it("draws a name that fits at the full size", () => {
    // Every block id in the repo is this short or shorter, so the shrink is a
    // safety net rather than the usual case.
    for (const name of ["C4", "CE1", "station_a_1", "line_yellow"]) {
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

describe("the label a portal pairing with nothing wears", () => {
  /** How far the outer stroke of the mouth reaches along the track, the two
   *  strokes leaning away from it as they cross. */
  const mouth =
    PORTAL.mouth.first +
    PORTAL.mouth.apart +
    Math.abs(PORTAL.lean) * PORTAL.mouth.reach;

  it("begins past the mouth, clear of the artwork it marks", () => {
    // The point is where the label starts, not where it is centred, so this
    // is the clearance for a label of any length (geometry.ts's labelAnchor).
    expect(PORTAL.mark.x).toBeGreaterThan(mouth);
  });

  it("sits outside the portal's own square, where no wire lands", () => {
    // The pin is on the other side, so the space past the mouth is the free
    // one whichever way the portal is turned.
    expect(PORTAL.mark.x).toBeGreaterThan(1);
  });

  it("stays on the track's centreline, so it reads as the mouth's", () => {
    expect(PORTAL.mark.y).toBe(0.5);
  });

  it("is smaller than a block's label, a portal being a smaller symbol", () => {
    expect(PORTAL.mark.size).toBeLessThan(LABEL.size);
  });
});
