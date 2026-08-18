import { describe, expect, it } from "vitest";

import { nameTrouble } from "../src/model/drawing.js";

describe("naming a new drawing", () => {
  it("accepts a fresh name", () => {
    expect(nameTrouble("gotthard-meet", ["gotthard"])).toBeNull();
  });

  it("refuses a taken name, so a fork never clobbers the original", () => {
    expect(nameTrouble("gotthard", ["gotthard"])).toContain("already");
  });

  it("refuses a slash, which the file path cannot carry", () => {
    expect(nameTrouble("a/b", [])).toContain("cannot name a file");
  });
});
