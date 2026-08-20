/**
 * The panel's static view of a drawing: the fitted viewBox and the pose of a
 * direction arrow. Pure geometry, tested as numbers in, numbers out.
 */

import { describe, expect, it } from "vitest";

import type { Drawing } from "../src/model/drawing.js";
import type { Position } from "../src/symbols.generated.js";
import { arrowPose, fitBox, lying } from "../src/model/scene.js";

describe("fitBox", () => {
  it("frames every pin with a margin and headroom for notes", () => {
    const drawing: Drawing = {
      drawing: "scene",
      symbols: { b1: { kind: "block", at: [2, 3], length: 1000 } },
      wires: [],
    };
    // A block's pins sit at (2, 3.5) and (8, 3.5).
    expect(fitBox(drawing)).toEqual({ x: 1, y: 2, w: 8, h: 3 });
  });

  it("gives an empty drawing somewhere to look", () => {
    const drawing: Drawing = { drawing: "scene", symbols: {}, wires: [] };
    expect(fitBox(drawing)).toEqual({ x: -1, y: -1, w: 16, h: 11 });
  });
});

describe("arrowPose", () => {
  const block = { kind: "block" as const, at: [0, 0] as [number, number] };

  it("sits ahead of the centre, pointing at the end the train faces", () => {
    // Centre (3, 0.5), pin B at (6, 0.5): due east.
    const pose = arrowPose(block, "B");
    expect(pose.x).toBeCloseTo(4.1);
    expect(pose.y).toBeCloseTo(0.5);
    expect(pose.angle).toBeCloseTo(0);
  });

  it("turns with the facing and with the symbol", () => {
    expect(Math.abs(arrowPose(block, "A").angle)).toBeCloseTo(180);
    const turned = { ...block, rot: 90 as const };
    expect(Math.abs(arrowPose(turned, "B").angle)).toBeCloseTo(90);
  });
});

/**
 * Where each point on the sheet lies: the alignment command's addresses read
 * back as the symbols wearing them (#98).
 */
describe("lying", () => {
  const drawing: Drawing = {
    drawing: "yard",
    symbols: {
      sw1: { kind: "turnout", at: [0, 0], addr: "12" },
      sw2: { kind: "turnout", at: [3, 0], addr: "12" },
      sw3: { kind: "turnout", at: [6, 0], addr: "13" },
      sw4: { kind: "turnout", at: [9, 0] },
      x1: { kind: "crossing", at: [12, 0] },
      b1: { kind: "block", at: [0, 3], length: 1000 },
    },
    wires: [],
  };

  const commanded = new Map<string, Position>([
    ["12", "thrown"],
    ["13", "closed"],
  ]);

  it("puts an address on every symbol wearing it", () => {
    // Two points on one address answer to one accessory output and move
    // together (ADR-0022), so both lie the way it was commanded.
    expect(lying(drawing, commanded)).toEqual(
      new Map([
        ["sw1", "thrown"],
        ["sw2", "thrown"],
        ["sw3", "closed"],
      ]),
    );
  });

  it("leaves an address no symbol wears out of it", () => {
    // The railroad is wired by hand and the drawing is edited by hand, so a
    // command can name an address this drawing knows nothing about. It is
    // one point the panel cannot show, not a panel that cannot draw.
    expect(lying(drawing, new Map([["99", "thrown"]]))).toEqual(new Map());
  });

  it("says nothing about a point no command has named", () => {
    expect(lying(drawing, new Map()).size).toBe(0);
  });
});
