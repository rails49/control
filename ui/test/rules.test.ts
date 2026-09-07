/**
 * The store's rules over a document, as the browser has them
 * (`model/rules.ts`).
 *
 * No DOM: each is a rule and a rule belongs where it can be driven from plain
 * values (ui/README.md). What is pinned is the transcription — the same
 * strings `tc49.lib.layout.check_name` and `check_length` take and refuse —
 * because a browser that is more permissive than the store answers a typed
 * value with a 400 from across the network instead of beside the field.
 */

import { describe, expect, it } from "vitest";

import { isName, lengthTrouble } from "../src/model/rules.js";

describe("a name a document may be filed under", () => {
  it("is a string with something in it", () => {
    expect(isName("b1")).toBe(true);
    expect(isName("")).toBe(false);
  });

  /** The `.` separates a symbol from its pin and the `/` separates a path, so
   *  a name wearing either would be read as two things. */
  it("carries neither the pin separator nor the path separator", () => {
    expect(isName("b1.A")).toBe(false);
    expect(isName("layouts/b1")).toBe(false);
  });
});

describe("a length", () => {
  it("is nothing to say about a positive whole number of millimetres", () => {
    expect(lengthTrouble(1)).toBeNull();
    expect(lengthTrouble(1000)).toBeNull();
  });

  it("is refused at zero, below it, and between two whole numbers", () => {
    for (const mm of [0, -1, 12.5, Number.NaN]) {
      expect(lengthTrouble(mm)).toBe(
        "a length is a positive whole number of millimetres",
      );
    }
  });
});
