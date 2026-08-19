import { describe, expect, it } from "vitest";

import {
  motorised,
  named,
  nameTrouble,
  symbolTrouble,
} from "../src/model/drawing.js";

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

/**
 * Which kinds a name is typed on (ADR-0023). A name is typed only where a
 * person has to say it out loud, and the motorised kinds are not that: the bus
 * addresses `addr`, not the key (ADR-0022), so their names are minted and
 * hidden like a crossing's.
 */
describe("the kinds whose name is the user's to choose", () => {
  it("names a block, which the operator says out loud", () => {
    expect(named("block")).toBe(true);
  });

  it("does not name a turnout", () => {
    expect(named("turnout")).toBe(false);
  });

  it("does not name a single slip", () => {
    expect(named("single_slip")).toBe(false);
  });

  it("does not name a double slip", () => {
    expect(named("double_slip")).toBe(false);
  });

  /** Unchanged: this is felt only where a name was being asked for. */
  it("leaves the wiring and the fixed crossing unnamed as they were", () => {
    for (const kind of ["pin", "terminal", "portal", "crossing"] as const) {
      expect(named(kind)).toBe(false);
    }
  });
});

/**
 * Which kinds carry an address (ADR-0022). A motorised symbol is commanded by
 * the address hardware answers to, so it is the one thing typed on a turnout
 * or a slip; a fixed crossing has no motor and takes none.
 */
describe("the kinds that carry an address", () => {
  it("addresses every kind with a motor", () => {
    for (const kind of ["turnout", "single_slip", "double_slip"] as const) {
      expect(motorised(kind)).toBe(true);
    }
  });

  it("leaves a fixed crossing unaddressed, having no motor to command", () => {
    for (const kind of ["crossing", "crossing_90", "crossing_90d"] as const) {
      expect(motorised(kind)).toBe(false);
    }
  });

  it("addresses nothing that is not a symbol of fixed geometry", () => {
    for (const kind of ["block", "portal", "pin", "terminal", "connection"] as const) {
      expect(motorised(kind)).toBe(false);
    }
  });
});

/**
 * Why a symbol name will not do, asked in the properties dialog before it
 * closes rather than reported afterwards (ADR-0023). One assertion per reason,
 * the way the drawing-name predicate above is covered.
 */
describe("renaming a symbol", () => {
  it("accepts a name the drawing does not have", () => {
    expect(symbolTrouble("claro_2", "b1", ["b1", "claro_1"])).toBeNull();
  });

  /** Applying a dialog nothing was typed into is not a rename. */
  it("accepts the name the symbol already wears", () => {
    expect(symbolTrouble("b1", "b1", ["b1", "claro_1"])).toBeNull();
  });

  it("refuses a name the drawing already has, saying which", () => {
    expect(symbolTrouble("claro_1", "b1", ["b1", "claro_1"])).toBe(
      "'claro_1' is already taken",
    );
  });

  it("refuses an empty name", () => {
    expect(symbolTrouble("", "b1", ["b1"])).toContain("needs a name");
  });

  it("refuses the dot that separates a symbol from its pin", () => {
    expect(symbolTrouble("b1.A", "b1", ["b1"])).toContain("cannot name");
  });

  it("refuses the slash a path is split on", () => {
    expect(symbolTrouble("a/b", "b1", ["b1"])).toContain("cannot name");
  });
});
