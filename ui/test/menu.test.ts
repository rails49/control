// @vitest-environment happy-dom

/**
 * The right-click menu offers what applies to whatever was clicked, and
 * nothing where nothing does.
 *
 * A DOM test, the whole of the behaviour being what the component renders.
 * The items are the editor's — `tc-menu` renders a list it is given (#124) —
 * so the two are exercised together, exactly as the shell wires them.
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-menu.js";
import type { MenuItem } from "../src/ui/tc-menu.js";
import { editorMenu, type MenuAt } from "../src/ui/tc-editor.js";
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

/** The items the menu draws for what was clicked, as the editor works them
 *  out and hands them over. */
async function items(what: MenuAt | null): Promise<string[]> {
  return (await drawn(what, what === null ? [] : editorMenu(what))).map((button) =>
    button.querySelector("span")!.textContent!.trim(),
  );
}

/** The rows a menu given these items renders. */
async function drawn(
  what: { x: number; y: number } | null,
  offered: MenuItem[],
): Promise<HTMLButtonElement[]> {
  const menu = document.createElement("tc-menu");
  menu.at = what;
  menu.items = offered;
  document.body.append(menu);
  await menu.updateComplete;
  return [...menu.renderRoot.querySelectorAll<HTMLButtonElement>("li button")];
}

describe("what the menu offers", () => {
  it("offers a symbol its properties and the transforms", async () => {
    expect(await items(at({ symbol: "b1", kind: "block" }))).toEqual([
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

  /** A turnout and a slip have no name to type — the bus addresses `addr` and
   *  not the key (ADR-0022) — but the address itself is theirs to set, so the
   *  dialog opens holding that alone. */
  it("offers the motorised kinds their properties and the transforms", async () => {
    for (const kind of ["turnout", "single_slip", "double_slip"] as const) {
      expect(await items(at({ symbol: "sw1", kind }))).toEqual([
        "Properties…",
        "Rotate",
        "Flip",
        "Delete",
      ]);
    }
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
    menu.items = editorMenu(at());
    document.body.append(menu);
    await menu.updateComplete;
    expect(menu.renderRoot.querySelector("menu")).toBeNull();
  });

  it("says so of what was clicked", () => {
    expect(editorMenu(at())).toEqual([]);
    expect(editorMenu(at({ symbol: "sw1", kind: "turnout" }))).not.toEqual([]);
    expect(editorMenu(at({ wire: ["b1.A", "b2.B"] }))).not.toEqual([]);
    expect(editorMenu(at({ junction: JUNCTION }))).toEqual([]);
    expect(editorMenu(at({ joint: JOINT }))).toEqual([]);
  });
});

/**
 * An item may be offered and not choosable: the panel greys "Turn around"
 * while the train has a request in flight (#124), which says *this train is
 * busy* where leaving the item out would say nothing at all.
 */
describe("an item that does not apply just now", () => {
  it("is drawn disabled, and the rest are not", async () => {
    const [busy, free] = await drawn({ x: 10, y: 10 }, [
      { label: "Turn around", action: "turn-around", disabled: true },
      { label: "Something else", action: "else" },
    ]);
    expect(busy!.disabled).toBe(true);
    expect(free!.disabled).toBe(false);
  });
});
