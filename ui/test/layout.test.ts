/**
 * The layout document as the browser types it, against what the store emits
 * (`store/drawing.py`, `derive`).
 *
 * Nothing in the app reads a signal address or a transit's points off a
 * layout: the run view is told which points to throw on `align`, and an
 * aspect arrives on its own topic. What the shape is for is that a view which
 * comes to read one finds it typed rather than absent — a field the store
 * emits and the type does not have is a field TypeScript refuses to look at,
 * which is how a browser ends up deriving what the store already said
 * (ADR-0031, ADR-0022).
 *
 * So this is a type test with a value in it: `tsc` is what it is really
 * asking, and the assertions are there so the literal is not dead code.
 */

import { describe, expect, it } from "vitest";

import { transitEnds, type Layout } from "../src/model/store.js";

/** One block with a signal at each end and one connection whose way needs
 *  points thrown: the two optional keys, both present. */
const YARD: Layout = {
  layout: "yard",
  blocks: {
    a: { length: 1200, signals: { A: "40", B: "41" } },
    b: { length: 900 },
  },
  connections: {
    j1: {
      transits: { a_B__b_A: ["a.B", "b.A"] },
      points: { a_B__b_A: [{ addr: "31", position: "thrown" }] },
    },
    j2: { transits: { b_B__a_A: ["b.B", "a.A"] } },
  },
};

describe("the layout document", () => {
  it("carries the address of the signal standing at a block end", () => {
    expect(YARD.blocks.a!.signals).toEqual({ A: "40", B: "41" });
  });

  /** Absent rather than empty where nothing stands there: the store writes
   *  the key only for a block that has any. */
  it("says nothing of a block no signal stands at", () => {
    expect(YARD.blocks.b!.signals).toBeUndefined();
  });

  it("carries the points a way needs thrown, by transit", () => {
    expect(YARD.connections.j1!.points).toEqual({
      a_B__b_A: [{ addr: "31", position: "thrown" }],
    });
    expect(YARD.connections.j2!.points).toBeUndefined();
  });

  it("still answers the ends a transit joins", () => {
    expect(transitEnds(YARD, "j1.a_B__b_A")).toEqual(["a.B", "b.A"]);
  });
});
