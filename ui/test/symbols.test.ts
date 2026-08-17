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

  it("declares a transit between two pins the same kind has", () => {
    for (const [kind, legs] of Object.entries(TRANSITS)) {
      const pins: readonly string[] = PINS[kind as LibraryKind];
      for (const pair of Object.values(legs)) {
        expect(pins).toEqual(expect.arrayContaining([...pair]));
      }
    }
  });
});
