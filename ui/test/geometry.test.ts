import { describe, expect, it } from "vitest";

import type { SymbolSpec } from "../src/model/drawing.js";
import {
  anchorOf,
  cellsOf,
  faceAt,
  gridPointOf,
  placed,
} from "../src/model/geometry.js";

describe("footprints and pins", () => {
  it("puts a block's ends on the two short faces", () => {
    const block: SymbolSpec = { kind: "block", at: [3, 4] };
    expect(anchorOf(block, "A")).toEqual({ x: 3, y: 4.5 });
    expect(anchorOf(block, "B")).toEqual({ x: 9, y: 4.5 });
  });

  it("turns the footprint with the symbol", () => {
    expect(placed({ kind: "block", rot: 90 }).footprint).toEqual({
      w: 1,
      h: 6,
    });
    expect(placed({ kind: "block", rot: 180 }).footprint).toEqual({
      w: 6,
      h: 1,
    });
  });

  it("carries the pins round with it", () => {
    const at: [number, number] = [0, 0];
    expect(anchorOf({ kind: "block", at, rot: 90 }, "A")).toEqual({
      x: 0.5,
      y: 0,
    });
    expect(anchorOf({ kind: "block", at, rot: 90 }, "B")).toEqual({
      x: 0.5,
      y: 6,
    });
    expect(anchorOf({ kind: "block", at, rot: 180 }, "A")).toEqual({
      x: 6,
      y: 0.5,
    });
  });

  it("brings every pin back where it started after four turns", () => {
    let spec: SymbolSpec = { kind: "turnout", at: [2, 2] };
    const before = ["toe", "straight", "diverging"].map((pin) =>
      anchorOf(spec, pin),
    );
    for (let turn = 0; turn < 4; turn++) {
      spec = { ...spec, rot: (((spec.rot ?? 0) + 90) % 360) as 0 | 90 | 180 };
    }
    expect(["toe", "straight", "diverging"].map((pin) => anchorOf(spec, pin)))
      .toEqual(before);
  });

  it("mirrors a turnout's diverging leg without moving its toe", () => {
    const at: [number, number] = [0, 0];
    expect(anchorOf({ kind: "turnout", at, flip: true }, "toe")).toEqual({
      x: 1,
      y: 0.5,
    });
    expect(anchorOf({ kind: "turnout", at, flip: true }, "diverging")).toEqual({
      x: 0.5,
      y: 0,
    });
  });

  it("keeps every pin at a face centre, whatever the placement", () => {
    for (const kind of [
      "block",
      "turnout",
      "crossing",
      "crossing_90",
      "crossing_90d",
      "single_slip",
      "double_slip",
      "terminal",
      "portal",
    ] as const) {
      for (const rot of [0, 90, 180, 270] as const) {
        for (const flip of [false, true]) {
          const spec: SymbolSpec = { kind, at: [1, 1], rot, flip };
          for (const pin of Object.keys(placed(spec).anchors)) {
            const { x, y } = anchorOf(spec, pin);
            expect(Number.isInteger(x) !== Number.isInteger(y)).toBe(true);
          }
        }
      }
    }
  });

  it("covers whole squares, and none at all for a bend", () => {
    expect(cellsOf({ kind: "block", at: [1, 1] })).toHaveLength(6);
    expect(cellsOf({ kind: "turnout", at: [1, 1] })).toEqual([[1, 1]]);
    expect(cellsOf({ kind: "crossing", at: [0, 0] })).toEqual([
      [0, 0],
      [1, 0],
    ]);
    expect(cellsOf({ kind: "pin", at: [5, 5] })).toEqual([]);
  });

  it("crosses its two routes where the artwork does", () => {
    // The frog is the face centre the two squares share, which is what makes
    // the crossing exactly two turnouts toe to toe (EDITOR.md).
    for (const kind of ["crossing", "crossing_90", "crossing_90d"] as const) {
      const spec: SymbolSpec = { kind };
      const middle = (a: string, b: string) => {
        const [from, to] = [anchorOf(spec, a), anchorOf(spec, b)];
        return { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
      };
      expect(middle("a1", "a2")).toEqual(middle("b1", "b2"));
    }
  });
});

describe("a point of the symbol's own coordinates", () => {
  it("lands where the placement puts it", () => {
    // What lets a portal's label be drawn upright beside a mouth that turned.
    const mouth = { x: 0.9, y: 0.5 };
    expect(gridPointOf({ kind: "portal", at: [2, 3] }, mouth)).toEqual({
      x: 2.9,
      y: 3.5,
    });
    expect(
      gridPointOf({ kind: "portal", at: [2, 3], rot: 180 }, mouth),
    ).toEqual({ x: 2.1, y: 3.5 });
  });

  it("agrees with the anchors, which are points like any other", () => {
    for (const rot of [0, 90, 180, 270] as const) {
      for (const flip of [false, true]) {
        const spec: SymbolSpec = { kind: "turnout", at: [1, 2], rot, flip };
        expect(gridPointOf(spec, { x: 0.5, y: 0 })).toEqual(
          anchorOf(spec, "diverging"),
        );
      }
    }
  });
});

describe("the generic connection symbol", () => {
  const claro: SymbolSpec = {
    kind: "connection",
    at: [2, 2],
    pins: ["a", "b", "c", "d", "e"],
  };

  it("takes a box tall enough for the pins it declares", () => {
    // It is legacy and not on the palette, but a drawing that still has one
    // has to open, so it needs a footprint the library cannot give it.
    expect(placed(claro).footprint).toEqual({ w: 2, h: 3 });
    expect(Object.keys(placed(claro).anchors)).toHaveLength(5);
  });

  it("puts every one of them on a face, half down each side", () => {
    expect(anchorOf(claro, "a")).toEqual({ x: 2, y: 2.5 });
    expect(anchorOf(claro, "c")).toEqual({ x: 2, y: 4.5 });
    expect(anchorOf(claro, "d")).toEqual({ x: 4, y: 2.5 });
  });

  it("turns like anything else", () => {
    expect(placed({ ...claro, rot: 90 }).footprint).toEqual({ w: 3, h: 2 });
  });
});

describe("placing a bend", () => {
  it("snaps to the nearest face centre", () => {
    expect(faceAt(2.05, 3.5)).toEqual({ at: [2, 3], rot: 0 });
    expect(faceAt(2.5, 3.05)).toEqual({ at: [2, 3], rot: 90 });
  });

  it("gives a face one spelling, so the same click writes the same bend", () => {
    // A face is shared by two cells. Snapping the point just either side of a
    // west face has to give the cell to its east both times.
    expect(faceAt(2.01, 3.5)).toEqual(faceAt(1.99, 3.5));
  });

  it("lands the bend on the face it snapped to", () => {
    for (const [x, y] of [
      [4.4, 2.6],
      [0.1, 0.9],
      [7.5, 7.5],
    ]) {
      const { at, rot } = faceAt(x!, y!);
      const { x: px, y: py } = anchorOf({ kind: "pin", at, rot }, "P");
      expect(Math.hypot(px - x!, py - y!)).toBeLessThanOrEqual(0.75);
    }
  });
});
