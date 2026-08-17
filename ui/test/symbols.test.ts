import { describe, expect, it } from "vitest";

import {
  PINS,
  PLACEABLE,
  TRANSITS,
  type Kind,
  type Leg,
  type LibraryKind,
  type Pin,
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

  it("keeps the bend off the palette and everything else on it", () => {
    const placeable: readonly Kind[] = PLACEABLE;
    expect([...placeable].sort()).toEqual(
      Object.keys(PINS)
        .filter((kind) => kind !== "pin")
        .sort(),
    );
  });

  it("gives every placeable kind a place in the palette, and no other", () => {
    // The palette is drawn in EDITOR.md's order, which is not the generator's,
    // so a new placeable kind would otherwise be silently left off.
    expect([...PALETTE].sort()).toEqual([...PLACEABLE].sort());
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
  it("draws each declared leg as a stroke of its own", () => {
    for (const [kind, legs] of Object.entries(TRANSITS)) {
      const spec = { kind } as SymbolSpec;
      expect(litStrokes(artwork(spec))).toEqual([]);
      expect(litStrokes(artwork(spec, new Set([WHOLE])))).toHaveLength(
        Object.keys(legs).length,
      );
      for (const leg of Object.keys(legs)) {
        expect(litStrokes(artwork(spec, new Set([leg])))).toHaveLength(1);
      }
    }
  });
});

describe("the artwork of the generic connection symbol", () => {
  it("lights the box whenever a way takes any of its legs", () => {
    // It declares real transits, so a way through it names one — and the box
    // draws no leg to light. Keyed on the joiner marker it would never light
    // at all, and a lit run would read as broken where it crosses one.
    const spec = { kind: "connection", pins: ["a", "b"] } as SymbolSpec;
    expect(litStrokes(artwork(spec))).toEqual([]);
    expect(litStrokes(artwork(spec, new Set(["blue_2_1"])))).toHaveLength(1);
    expect(litStrokes(artwork(spec, new Set([WHOLE])))).toHaveLength(1);
  });
});

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
