/**
 * When the settings dialog's railroad part is refused, with no DOM (#733).
 *
 * The first condition that holds is the reason, so each row of the table is
 * checked with every row below it also holding: the order is the claim.
 */

import { describe, expect, it } from "vitest";

import { refusal } from "../src/model/settings.js";

describe("why the railroad part is refused", () => {
  it("is refused while the layout has not said which railroad is loaded", () => {
    expect(refusal(null, "on", "the drawing")).toBe(
      "the layout has not said which railroad is loaded",
    );
    expect(refusal(null, "off", null)).toBe(
      "the layout has not said which railroad is loaded",
    );
  });

  it.each(["on", "stopped", null] as const)(
    "is refused while a railroad is loaded and the track reads %s",
    (power) => {
      expect(refusal("otira", power, "the drawing")).toBe(
        "the track has power: switch it off to load another railroad",
      );
    },
  );

  it("is refused over unsaved edits, naming what holds them", () => {
    expect(refusal("otira", "off", "the drawing")).toBe(
      "the drawing has unsaved edits — save first",
    );
    expect(refusal("", null, "the roster")).toBe(
      "the roster has unsaved edits — save first",
    );
  });

  it("is open with the track dead and nothing unsaved", () => {
    expect(refusal("otira", "off", null)).toBeNull();
  });

  /** A binding with nothing loaded reads no supply, and the first railroad on
   *  a new box is loaded from the dialog (ADR-0072, decision 6). */
  it("is open with no railroad loaded, whatever the supply has said", () => {
    expect(refusal("", null, null)).toBeNull();
  });
});
