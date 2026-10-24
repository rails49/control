/**
 * How many throttles a throttle view shows side by side, and how wide each
 * is (ui/THROTTLE.md, ADR-0089): a phone-sized panel no wider than 440 px, at
 * least 360 px beside another, 20 px between them and 8 px round the row. No
 * DOM — the view reads its own size and asks this.
 */

import { describe, expect, it } from "vitest";

import { panelHeight, panels } from "../src/model/throttle.js";

describe("panels", () => {
  it.each([
    [360, { count: 1, width: 360, single: true }],
    [440, { count: 1, width: 440, single: true }],
    [758, { count: 2, width: 361, single: false }],
    [1118, { count: 2, width: 440, single: false }],
    [1920, { count: 5, width: 364, single: false }],
  ])("lays %i px out as %j", (width, laid) => {
    expect(panels(width)).toEqual(laid);
  });
});

describe("panelHeight", () => {
  it("is the view's height, less the margin side by side", () => {
    expect(panelHeight(700, true)).toBe(700);
    expect(panelHeight(700, false)).toBe(684);
  });

  it("is clamped to 560–834 px", () => {
    expect(panelHeight(400, true)).toBe(560);
    expect(panelHeight(1200, false)).toBe(834);
  });
});
