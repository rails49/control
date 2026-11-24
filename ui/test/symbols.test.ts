import { describe, expect, it } from "vitest";

import {
  PINS,
  PLACEABLE,
  POSITIONS,
  TRANSITS,
  type Kind,
  type Leg,
  type LibraryKind,
  type MotorisedKind,
  type Pin,
  type Position,
} from "../src/symbols.generated.js";
import type { SymbolSpec } from "../src/model/drawing.js";
import { WHOLE } from "../src/model/inspect.js";
import { PALETTE, artwork } from "../src/render/artwork.js";

/**
 * The generated file is a set of types as much as a set of values, and a type
 * that resolves to `never` is not a compile error where it is declared — only
 * where somebody tries to use it. These assignments are that somebody: they
 * are checked by `tsc --noEmit`, and the runtime assertions are what makes
 * vitest carry them.
 */
describe("the generated symbol library", () => {
  it("gives every pin of every kind one type", () => {
    const anyPin: Pin = "toe";
    const ofAKind: Pin<"crossing"> = "a1";
    expect([anyPin, ofAKind]).toEqual(["toe", "a1"]);
  });

  it("gives every leg of every kind one type", () => {
    // `keyof` over a union of the leg objects intersects their keys, and no
    // leg is common to all of them, so a naive `Leg` would be `never` and the
    // first line to use it would not compile.
    const anyLeg: Leg = "straight";
    const alsoAnyLeg: Leg = "slip_2";
    const ofAKind: Leg<"turnout"> = "diverging";
    expect([anyLeg, alsoAnyLeg, ofAKind]).toEqual([
      "straight",
      "slip_2",
      "diverging",
    ]);
  });

  it("gives every leg of a motorised kind the position it wants", () => {
    // No kind's legs are named for its positions, so this table is the only
    // place the editor can learn that `slip` and `diverging` mean thrown.
    const kind: MotorisedKind = "single_slip";
    const position: Position = POSITIONS[kind].slip;
    const turnout: Position = POSITIONS.turnout.diverging;
    expect([position, turnout]).toEqual(["thrown", "thrown"]);
  });

  it("keeps the bend off the palette and everything else on it", () => {
    const placeable: readonly Kind[] = PLACEABLE;
    expect([...placeable].sort()).toEqual(
      Object.keys(PINS)
        .filter((kind) => kind !== "pin")
        .sort(),
    );
  });

  it("gives every placeable kind a place in the palette, and no other", () => {
    // The palette is drawn in EDITOR.md's groups, which are not the
    // generator's order, so a new placeable kind would otherwise be silently
    // left off.
    expect(PALETTE.flat(2).sort()).toEqual([...PLACEABLE].sort());
  });

  it("puts each kind in exactly one group", () => {
    const placed = PALETTE.flat(2);
    expect(new Set(placed).size).toBe(placed.length);
  });

  it("declares a transit between two pins the same kind has", () => {
    for (const [kind, legs] of Object.entries(TRANSITS)) {
      const pins: readonly string[] = PINS[kind as LibraryKind];
      for (const pair of Object.values(legs)) {
        expect(pins).toEqual(expect.arrayContaining([...pair]));
      }
    }
  });
});

/**
 * A leg with no stroke of its own is the silent failure here: the way a
 * chosen transit takes is lit leg by leg, so a leg the artwork draws as part
 * of another one simply never lights, and the netlist claims a movement the
 * picture does not show. That is invisible until somebody clicks the one
 * transit that takes it, which is why it is asserted for every kind.
 */
describe("the artwork of a symbol whose legs the library fixes", () => {
  it("lights something for each declared leg, and nothing for none", () => {
    for (const [kind, legs] of Object.entries(TRANSITS)) {
      const spec = { kind } as SymbolSpec;
      expect(litStrokes(artwork(spec))).toEqual([]);
      for (const leg of Object.keys(legs)) {
        expect(litStrokes(artwork(spec, new Set([leg])))).not.toHaveLength(0);
      }
    }
  });

  it("lights a leg as its one stroke", () => {
    // Every leg is one stroke from pin to pin (#1295), so a lit slip road is
    // its curve alone and not the through routes it leaves and joins.
    const crossing = { kind: "crossing" } as SymbolSpec;
    expect(litStrokes(artwork(crossing, new Set(["a"])))).toHaveLength(1);
    expect(litStrokes(artwork(crossing, new Set([WHOLE])))).toHaveLength(2);

    const slip = { kind: "single_slip" } as SymbolSpec;
    expect(litStrokes(artwork(slip, new Set(["slip"])))).toHaveLength(1);
    expect(litStrokes(artwork(slip, new Set([WHOLE])))).toHaveLength(3);
  });
});

/**
 * What the sample tiles fix about a symbol (EDITOR.md#symbol-geometry), asserted
 * as what is drawn rather than where: the geometry itself is tuned by eye, so
 * pinning coordinates would make every nudge a test edit.
 */
describe("the artwork the samples fix", () => {
  it("gives a block two signals, each a plaque with three lamps", () => {
    const block = written({ kind: "block" } as SymbolSpec);
    expect(times(block, `class="plaque"`)).toBe(2);
    for (const colour of ["green", "red", "amber"]) {
      expect(times(block, `class="lamp ${colour}"`)).toBe(2);
    }
    expect(block).not.toContain("mast");
  });

  it("marks a block's A end with one letter A and no plus", () => {
    const block = written({ kind: "block" } as SymbolSpec);
    expect(times(block, `class="end-a"`)).toBe(1);
    expect(block).toMatch(/>A<\/text>/);
    expect(block).not.toContain(`class="mark"`);
  });

  it("cuts a terminal's stub square, so it stays inside the bar", () => {
    expect(written({ kind: "terminal" } as SymbolSpec)).toContain("track cut");
  });

  it("clips a portal's stub, keeping it a stroke, and marks the mouth twice", () => {
    const portal = written({ kind: "portal" } as SymbolSpec);
    expect(portal).toContain("url(#portal-cut)");
    expect(times(portal, `class="portal-mouth"`)).toBe(2);
  });

  it("draws a slip road as track, a curve and no tick", () => {
    const slip = written({ kind: "single_slip" } as SymbolSpec);
    expect(times(slip, "tick")).toBe(0);
    expect(times(slip, "Q")).toBe(1);
    expect(times(written({ kind: "double_slip" } as SymbolSpec), "Q")).toBe(2);
    expect(times(written({ kind: "crossing" } as SymbolSpec), "Q")).toBe(0);
  });
});

/**
 * A track that meets another out of line at a pin is joined to it by a curve
 * that begins on the track (#1297). The symbol's strokes stop where the curve
 * begins and carry on round the symbol's half of it, to the middle. Where
 * that is, is `wiring`'s to say; here it is only drawn.
 */
describe("the artwork of a symbol a wire's corner cuts into", () => {
  const cut = (
    spec: SymbolSpec,
    pin: string,
    by: number,
    mid: { x: number; y: number } | undefined,
    lit?: string,
  ) =>
    flatten(
      artwork(
        spec,
        lit === undefined ? undefined : new Set([lit]),
        undefined,
        undefined,
        undefined,
        new Map([[pin, { by, mid }]]),
      ),
    );

  it("stops a block's stub short of the pin and carries it on round to the middle", () => {
    const whole = written({ kind: "block" } as SymbolSpec);
    const short = cut({ kind: "block" }, "B", 0.25, { x: 5.9, y: 0.6 });
    expect(whole).toContain("M5 0.5 L6 0.5");
    // The control point is half way between where the stub stops and the pin.
    expect(short).toContain("M5 0.5 L5.75 0.5 Q5.875 0.5 5.9 0.6");
    expect(short).toContain("M0 0.5 L1 0.5");
    expect(times(short, `class="plaque"`)).toBe(2);
    expect(short.replace("L5.75 0.5 Q5.875 0.5 5.9 0.6", "L6 0.5")).toBe(whole);
  });

  it("brings both of a turnout's roads round from the middle to its toe", () => {
    const short = cut({ kind: "turnout" }, "toe", 0.25, { x: -0.05, y: 0.6 });
    expect(short).toContain("M-0.05 0.6 Q0.125 0.5 0.25 0.5 L2 0.5");
    expect(short).toMatch(
      /M-0\.05 0\.6 Q0\.125 0\.5 0\.25 0\.5 L0\.293 0\.5\s+Q1 0\.5 1\.5 0/,
    );
  });

  it("lights the half with the road it ends, and no other", () => {
    const strokes = litStrokes(
      artwork(
        { kind: "turnout" },
        new Set(["diverging"]),
        undefined,
        undefined,
        undefined,
        new Map([["toe", { by: 0.25, mid: { x: -0.05, y: 0.6 } }]]),
      ),
    );
    expect(strokes).toEqual(["track lit"]);
  });

  it("cuts a diagonal leg along the diagonal", () => {
    // b2 is at (1.5, 0), up and right of the frog at (1, 0.5).
    const short = cut({ kind: "crossing" }, "b2", 0.2, { x: 1.6, y: -0.05 });
    expect(short).toContain("M0.5 1 L1.359 0.141 Q1.429 0.071 1.6 -0.05");
  });

  it("draws no dot at a bend the corner passes beside, lit or not", () => {
    expect(flatten(artwork({ kind: "pin" }, new Set([WHOLE])))).toContain("bend lit");
    expect(cut({ kind: "pin" }, "P", 0.5, undefined, WHOLE)).not.toContain("bend");
  });
});

/** Everything a symbol's template writes, interpolated values and the template
 *  around them alike: enough to say what is drawn, with no DOM to render into
 *  (EDITOR.md's tests). */
function written(spec: SymbolSpec): string {
  return flatten(artwork(spec));
}

function flatten(drawn: unknown): string {
  if (Array.isArray(drawn)) return drawn.map(flatten).join(" ");
  if (typeof drawn === "string" || typeof drawn === "number") {
    return String(drawn);
  }
  if (typeof drawn === "object" && drawn !== null && "values" in drawn) {
    const { strings, values } = drawn as {
      strings: readonly string[];
      values: unknown[];
    };
    return `${strings.join(" ")} ${values.map(flatten).join(" ")}`;
  }
  return "";
}

function times(text: string, what: string): number {
  return text.split(what).length - 1;
}

/** The class of every stroke a template lights. A template's values hold the
 *  classes; nested ones hold the rest, and there is no DOM here to render into
 *  (EDITOR.md's tests). */
function litStrokes(drawn: unknown): string[] {
  if (Array.isArray(drawn)) return drawn.flatMap(litStrokes);
  if (typeof drawn === "string") return drawn.includes("lit") ? [drawn] : [];
  if (typeof drawn === "object" && drawn !== null && "values" in drawn) {
    return (drawn.values as unknown[]).flatMap(litStrokes);
  }
  return [];
}
