/**
 * The panel's static view of a drawing: the fitted viewBox and the pose of a
 * direction arrow. Pure geometry, tested as numbers in, numbers out.
 */

import { describe, expect, it } from "vitest";

import type { Drawing } from "../src/model/drawing.js";
import { arrowPose, fitBox } from "../src/model/scene.js";

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
