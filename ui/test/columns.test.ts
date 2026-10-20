/**
 * How many trains a throttle view drives side by side (ui/THROTTLE.md, #855):
 * a train column is at least 360 px, the take column 260 px, and 14 px
 * between them. No DOM — the view reads its own width and asks this.
 */

import { describe, expect, it } from "vitest";

import { columns } from "../src/model/throttle.js";

describe("columns", () => {
  it.each([
    [390, 0],
    [820, 1],
    [1180, 2],
    [1920, 4],
  ])("fits %i px to %i train columns beside the take column", (width, fit) => {
    expect(columns(width)).toBe(fit);
  });

  it("is never fewer than none", () => {
    expect(columns(0)).toBe(0);
    expect(columns(100)).toBe(0);
  });

  it("gives a column exactly where one fits", () => {
    expect(columns(260 + 374 - 1)).toBe(0);
    expect(columns(260 + 374)).toBe(1);
  });
});
