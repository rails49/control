// @vitest-environment happy-dom

/**
 * The three dividers outside the run view
 * ([#1401](https://github.com/rails49/control/issues/1401)): the size a
 * client point means for each, held to its limits, and the size the browser
 * keeps.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { keep, kept, sizeAt } from "../src/model/divider.js";

/** A view's box: the work row, beside the rail and under the band. */
const BOX = {
  left: 50,
  right: 1050,
  top: 40,
  bottom: 740,
  width: 1000,
  height: 700,
} as DOMRect;

describe("the palette's divider", () => {
  it("sets the palette's width from the view's left edge", () => {
    expect(sizeAt("palette", BOX, { x: 350, y: 300 })).toBe(300);
  });

  /** The greatest leaves the drawing 256 px of the view's 1000. */
  it("holds it to 144 px and to what leaves the drawing 256 px", () => {
    expect(sizeAt("palette", BOX, { x: 60, y: 300 })).toBe(144);
    expect(sizeAt("palette", BOX, { x: 1040, y: 300 })).toBe(744);
  });
});

describe("the netlist's divider", () => {
  it("sets the netlist's width from the view's right edge", () => {
    expect(sizeAt("netlist", BOX, { x: 700, y: 300 })).toBe(350);
  });

  /** Against the view's whole width. The stylesheet holds the netlist
   *  against the palette as well. */
  it("holds it to 192 px and to 256 px short of the view's width", () => {
    expect(sizeAt("netlist", BOX, { x: 1040, y: 300 })).toBe(192);
    expect(sizeAt("netlist", BOX, { x: 60, y: 300 })).toBe(744);
  });
});

/**
 * The stock view's two boxes have 16 px left of the list, between the two
 * and right of the editor. The divider is the space between them, and the
 * point is its middle: 24 px from the view's left edge with the list.
 */
describe("the stock view's divider", () => {
  it("sets the list box's width", () => {
    expect(sizeAt("stock", BOX, { x: 474, y: 300 })).toBe(400);
  });

  /** The greatest leaves the editor box 320 px of the view's 1000, less
   *  the three spaces. */
  it("holds it to 300 px and to what leaves the editor box 320 px", () => {
    expect(sizeAt("stock", BOX, { x: 60, y: 300 })).toBe(300);
    expect(sizeAt("stock", BOX, { x: 1040, y: 300 })).toBe(632);
  });
});

describe("the size a divider was dragged to", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("is none until one is kept", () => {
    expect(kept("palette")).toBeNull();
    expect(kept("netlist")).toBeNull();
    expect(kept("stock")).toBeNull();
  });

  it("is kept in the browser under the divider's own key", () => {
    keep("palette", 300);
    keep("netlist", 350);
    keep("stock", 400);

    expect(kept("palette")).toBe(300);
    expect(kept("netlist")).toBe(350);
    expect(kept("stock")).toBe(400);
    expect(localStorage.getItem("tc49.palette")).toBe("300");
    expect(localStorage.getItem("tc49.netlist")).toBe("350");
    expect(localStorage.getItem("tc49.stock")).toBe("400");
  });
});

/** A browser that refuses the store throws on every read and write of it
 *  (#1414). */
describe("the size a divider was dragged to, in a browser that refuses the store", () => {
  beforeEach(() => {
    vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new DOMException("refused", "SecurityError");
    });
    vi.spyOn(localStorage, "setItem").mockImplementation(() => {
      throw new DOMException("refused", "SecurityError");
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is none, and keeping one does not throw", () => {
    expect(kept("palette")).toBeNull();
    expect(() => keep("palette", 300)).not.toThrow();
  });
});
