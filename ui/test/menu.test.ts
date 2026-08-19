// @vitest-environment happy-dom

/**
 * The right-click menu offers what applies to whatever was clicked, and
 * nothing where nothing does.
 *
 * A DOM test, the whole of the behaviour being what the component renders.
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-menu.js";
import { applies, type MenuAt } from "../src/ui/tc-menu.js";
import type { Joint, Junction } from "../src/model/store.js";

const JUNCTION: Junction = { name: "airolo", names: ["airolo"], symbols: ["sw1"] };
const JOINT: Joint = { ends: ["b1.A", "b2.B"], wires: [["b1.A", "b2.B"]], name: null, names: [] };

function at(parts: Partial<MenuAt> = {}): MenuAt {
  return {
    x: 10,
    y: 10,
    pin: null,
    symbol: null,
    kind: null,
    junction: null,
    joint: null,
    wire: null,
    ...parts,
  };
}

/** The items the menu draws for what was clicked. */
async function items(what: MenuAt | null): Promise<string[]> {
  const menu = document.createElement("tc-menu");
  menu.at = what;
  document.body.append(menu);
  await menu.updateComplete;
  return [...menu.renderRoot.querySelectorAll("li button span:first-child")].map(
    (span) => span.textContent!.trim(),
  );
}

describe("what the menu offers", () => {
  it("offers a symbol its properties and the transforms", async () => {
    expect(await items(at({ symbol: "sw1", kind: "turnout" }))).toEqual([
      "Properties…",
      "Rotate",
      "Flip",
      "Delete",
    ]);
  });

  /** A pin's name is minted and hidden and it has nothing else to set, so an
   *  empty dialog is all Properties could open. */
  it("offers a symbol with nothing to set only the transforms", async () => {
    expect(await items(at({ symbol: "n1", kind: "pin" }))).toEqual([
      "Rotate",
      "Flip",
      "Delete",
    ]);
  });

  /** A fixed crossing has no motor to name and, since transit names left the
   *  dialog (#82), nothing else to set either. */
  it("offers a fixed crossing only the transforms", async () => {
    for (const kind of ["crossing", "crossing_90", "crossing_90d"] as const) {
      expect(await items(at({ symbol: "x1", kind }))).toEqual([
        "Rotate",
        "Flip",
        "Delete",
      ]);
    }
  });

  /** A slip has a motor the bus addresses, so it keeps its name and its
   *  dialog with it. */
  it("still offers a slip its properties", async () => {
    expect(await items(at({ symbol: "sl1", kind: "double_slip" }))).toEqual([
      "Properties…",
      "Rotate",
      "Flip",
      "Delete",
    ]);
  });

  /** A junction's name is the editor's own: it mints one, keeps it settled
   *  through splits and merges, and shows it in the netlist pane. */
  it("offers a junction nothing", async () => {
    expect(await items(at({ junction: JUNCTION }))).toEqual([]);
  });

  it("offers a joint nothing", async () => {
    expect(await items(at({ joint: JOINT }))).toEqual([]);
  });

  /** A wire has no symbol to select and so no keystroke to take it: the menu
   *  is the only way to cut one. */
  it("offers a wire to be cut", async () => {
    expect(await items(at({ wire: ["b1.B", "sw1.toe"] }))).toEqual([
      "Delete wire",
    ]);
  });

  it("offers the wire of a joint the cut and no more", async () => {
    expect(await items(at({ joint: JOINT, wire: ["b1.A", "b2.B"] }))).toEqual([
      "Delete wire",
    ]);
  });
});

/** A wire is not a symbol, so right-clicking anywhere else lands on nothing at
 *  all. Drawing the menu anyway put an empty rounded box on the canvas. */
describe("nothing under the pointer", () => {
  it("draws no menu at all", async () => {
    expect(await items(at())).toEqual([]);
    const menu = document.createElement("tc-menu");
    menu.at = at();
    document.body.append(menu);
    await menu.updateComplete;
    expect(menu.renderRoot.querySelector("menu")).toBeNull();
  });

  it("says so of what was clicked", () => {
    expect(applies(at())).toBe(false);
    expect(applies(at({ symbol: "sw1", kind: "turnout" }))).toBe(true);
    expect(applies(at({ wire: ["b1.A", "b2.B"] }))).toBe(true);
    expect(applies(at({ junction: JUNCTION }))).toBe(false);
    expect(applies(at({ joint: JOINT }))).toBe(false);
  });
});
