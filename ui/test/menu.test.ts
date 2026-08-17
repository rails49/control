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
  return { x: 10, y: 10, symbol: null, junction: null, joint: null, ...parts };
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
    expect(await items(at({ symbol: "sw1" }))).toEqual([
      "Properties…",
      "Rotate",
      "Flip",
      "Delete",
    ]);
  });

  it("offers a junction its name", async () => {
    expect(await items(at({ junction: JUNCTION }))).toEqual([
      'Rename junction "airolo"',
    ]);
  });

  it("offers a joint the name of the connection it is", async () => {
    expect(await items(at({ joint: JOINT }))).toEqual([
      'Rename connection "unnamed"',
    ]);
  });
});

/** A wire is not a symbol, and only the bare wire between two blocks is a
 *  joint, so right-clicking any other wire lands on nothing at all. Drawing
 *  the menu anyway put an empty rounded box on the canvas. */
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
    expect(applies(at({ symbol: "sw1" }))).toBe(true);
    expect(applies(at({ junction: JUNCTION }))).toBe(true);
    expect(applies(at({ joint: JOINT }))).toBe(true);
  });
});
