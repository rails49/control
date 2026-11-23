import { describe, expect, it } from "vitest";

import type { SymbolSpec } from "../src/model/drawing.js";
import {
  anchorOf,
  cellsOf,
  faceAt,
  facePoint,
  gridPointOf,
  labelAnchor,
  labelTurn,
  placed,
  turned,
} from "../src/model/geometry.js";
import { TURNOUT_ROTATIONS } from "../src/symbols.generated.js";

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

  it("mirrors a turnout across its footprint", () => {
    const at: [number, number] = [0, 0];
    expect(anchorOf({ kind: "turnout", at, flip: true }, "toe")).toEqual({
      x: 2,
      y: 0.5,
    });
    expect(anchorOf({ kind: "turnout", at, flip: true }, "diverging")).toEqual({
      x: 0.5,
      y: 0,
    });
  });

  it("gives a turnout a slip's two squares and three of its pin sites", () => {
    // #1295's table: unturned the straight road is the horizontal, and at 45
    // degrees it is the diagonal of the mirrored slip.
    const pins = (spec: SymbolSpec) =>
      ["toe", "straight", "diverging"].map((pin) => anchorOf(spec, pin));
    expect(pins({ kind: "turnout" })).toEqual([
      { x: 0, y: 0.5 },
      { x: 2, y: 0.5 },
      { x: 1.5, y: 0 },
    ]);
    expect(pins({ kind: "turnout", rot: 45 })).toEqual([
      { x: 0.5, y: 0 },
      { x: 1.5, y: 1 },
      { x: 2, y: 0.5 },
    ]);
    const slip = (spec: SymbolSpec) =>
      ["a1", "a2", "b1", "b2"].map((pin) => anchorOf(spec, pin));
    expect(slip({ kind: "single_slip" })).toEqual(
      expect.arrayContaining(pins({ kind: "turnout" })),
    );
    expect(slip({ kind: "single_slip", flip: true })).toEqual(
      expect.arrayContaining(pins({ kind: "turnout", rot: 45 })),
    );
  });

  it("turns a turnout through 16 orientations, all on face centres", () => {
    const heading = (from: { x: number; y: number }, to: { x: number; y: number }) =>
      (Math.round((Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI) + 360) % 360;
    const span = (from: { x: number; y: number }, to: { x: number; y: number }) =>
      Math.hypot(to.x - from.x, to.y - from.y);
    const seen = new Set<string>();
    for (const rot of TURNOUT_ROTATIONS) {
      for (const flip of [false, true]) {
        const spec: SymbolSpec = { kind: "turnout", rot, flip };
        const { footprint, anchors } = placed(spec);
        const [toe, straight, diverging] = [
          anchors.toe!,
          anchors.straight!,
          anchors.diverging!,
        ];
        const where = `rot ${rot}${flip ? " flip" : ""}`;
        seen.add(JSON.stringify([toe, straight, diverging]));

        // Each pin is the centre of a face on the footprint's edge.
        for (const { x, y } of [toe, straight, diverging]) {
          const onSide = (x === 0 || x === footprint.w) && y % 1 === 0.5;
          const onEnd = (y === 0 || y === footprint.h) && x % 1 === 0.5;
          expect(onSide || onEnd, where).toBe(true);
        }

        // The frog is the face centre the two squares share.
        const frog = { x: (toe.x + straight.x) / 2, y: (toe.y + straight.y) / 2 };
        expect(frog, where).toEqual({ x: footprint.w / 2, y: footprint.h / 2 });

        // `rot` is the straight road's heading, clockwise from east, and the
        // diverging road leaves 45 degrees to its left; a flip mirrors both.
        const mirrored = (180 - (rot % 90) + rot - (rot % 90)) % 360;
        const along = heading(toe, straight);
        expect(along, where).toBe(flip ? mirrored : rot);
        expect(heading(frog, diverging), where).toBe(
          (along + (flip ? 45 : 315)) % 360,
        );
        expect(span(toe, straight), where).toBeCloseTo(
          along % 90 === 0 ? 2 : Math.SQRT2,
        );
        expect(span(frog, diverging), where).toBeCloseTo(
          along % 90 === 0 ? Math.SQRT1_2 : 1,
        );
      }
    }
    expect(seen.size).toBe(16);
  });

  it("steps a turnout by 45 degrees and every other kind by 90", () => {
    let turnout: SymbolSpec = { kind: "turnout" };
    const steps: (number | undefined)[] = [];
    for (let step = 0; step < 8; step++) {
      turnout = turned(turnout);
      steps.push(turnout.rot);
    }
    expect(steps).toEqual([45, 90, 135, 180, 225, 270, 315, 0]);
    for (const kind of ["single_slip", "double_slip", "crossing", "block"] as const) {
      expect(turned<SymbolSpec>({ kind }).rot).toBe(90);
      expect(turned<SymbolSpec>({ kind, rot: 270 }).rot).toBe(0);
    }
  });

  it("keeps a turnout's footprint through a 45 degree step", () => {
    expect(placed({ kind: "turnout", rot: 45 }).footprint).toEqual({ w: 2, h: 1 });
    expect(placed({ kind: "turnout", rot: 90 }).footprint).toEqual({ w: 1, h: 2 });
    expect(placed({ kind: "turnout", rot: 135 }).footprint).toEqual({ w: 1, h: 2 });
    expect(labelTurn({ kind: "turnout", rot: 45 })).toBe(0);
    expect(labelTurn({ kind: "turnout", rot: 135 })).toBe(-90);
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
    expect(cellsOf({ kind: "turnout", at: [1, 1] })).toEqual([
      [1, 1],
      [2, 1],
    ]);
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
        expect(gridPointOf(spec, { x: 1.5, y: 0 })).toEqual(
          anchorOf(spec, "diverging"),
        );
      }
    }
  });
});

describe("which end of an upright label sits on its point", () => {
  /** Where a portal's label goes: past the mouth, on the symbol's own +x. */
  const mark = { x: 1.2, y: 0.5 };

  it("starts the label where the point is east of the symbol", () => {
    expect(labelAnchor({ kind: "portal", at: [2, 3] }, mark)).toBe("start");
  });

  it("ends it where the placement put the point west", () => {
    // A portal turned 180 degrees has its mouth to the west, so a label
    // running east from the point would run back over the artwork.
    expect(labelAnchor({ kind: "portal", at: [2, 3], rot: 180 }, mark)).toBe(
      "end",
    );
    expect(labelAnchor({ kind: "portal", at: [2, 3], flip: true }, mark)).toBe(
      "end",
    );
  });

  it("centres it where the point is straight above or below", () => {
    for (const rot of [90, 270] as const) {
      expect(labelAnchor({ kind: "portal", at: [2, 3], rot }, mark)).toBe(
        "middle",
      );
    }
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

describe("how a label is turned", () => {
  it("leaves a horizontal block's label upright", () => {
    expect(labelTurn({ kind: "block" })).toBe(0);
    expect(labelTurn({ kind: "block", rot: 180 })).toBe(0);
  });

  it("reads a vertical block bottom to top, whichever way it stands", () => {
    // Both quarter turns give the same 1x6 footprint, and the label is not
    // the place to tell them apart: which end carries the A already says.
    expect(labelTurn({ kind: "block", rot: 90 })).toBe(-90);
    expect(labelTurn({ kind: "block", rot: 270 })).toBe(-90);
  });

  it("does not turn over when the block is flipped", () => {
    // reversing-loops's `CW` is `rot: 270, flip: true`. A flip that mirrored the
    // label would leave it unreadable rather than merely upside down.
    for (const rot of [0, 90, 180, 270] as const) {
      expect(labelTurn({ kind: "block", rot, flip: true })).toBe(
        labelTurn({ kind: "block", rot }),
      );
    }
  });
});

describe("where a bend dropped at a point would sit", () => {
  it("is the centre of the face the drop chooses", () => {
    // The wireline ends here and the sheet marks it, so the three have to be
    // the same point or the preview promises what the drop will not give.
    for (const [x, y] of [
      [0.1, 0.4],
      [3.9, 2.6],
      [-1.2, 5.7],
      [7, 7],
    ]) {
      const { at, rot } = faceAt(x!, y!);
      expect(facePoint(x!, y!)).toEqual(anchorOf({ kind: "pin", at, rot }, "P"));
    }
  });

  it("always lands on a face centre, never on a corner or a middle", () => {
    // Face centres are the points with one whole coordinate and one half one.
    for (let x = -2; x <= 4; x += 0.3) {
      for (let y = -2; y <= 4; y += 0.3) {
        const { x: fx, y: fy } = facePoint(x, y);
        const halves = [fx, fy].map((v) => Math.abs(v * 2 - Math.round(v * 2)));
        expect(Math.max(...halves)).toBeLessThan(1e-9);
        const whole = [fx, fy].filter((v) => Math.abs(v - Math.round(v)) < 1e-9);
        expect(whole.length).toBe(1);
      }
    }
  });

  it("is never more than half a square from the point asked about", () => {
    // Which is what the old 15 degree wireline could be wrong by: it drew to
    // the pointer's angle while the drop used the pointer's nearest face.
    for (let x = -1; x <= 3; x += 0.17) {
      for (let y = -1; y <= 3; y += 0.17) {
        const { x: fx, y: fy } = facePoint(x, y);
        expect(Math.hypot(fx - x, fy - y)).toBeLessThanOrEqual(0.5 + 1e-9);
      }
    }
  });
});
