// @vitest-environment happy-dom

/**
 * The edit view's two dividers and the stock view's
 * ([#1401](https://github.com/rails49/control/issues/1401)): right of the
 * palette, left of the netlist while it is open, and between the stock
 * view's list box and its editor box.
 *
 * happy-dom lays nothing out, so the suite states the view's box and reads
 * the sizes the view hands its stylesheet: `--palette-size`,
 * `--netlist-size` and `--list-size`.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { Point } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import { editing, pressed, running, settled, stocking } from "./support/shell.js";
import { brokering, joined, unbrokered } from "./support/session.js";

/** The view's own box: the work row, beside the rail and under the band. */
const BOX = {
  left: 50,
  right: 1050,
  top: 40,
  bottom: 740,
  width: 1000,
  height: 700,
} as DOMRect;

type View = HTMLElement & { renderRoot: ParentNode };

/** The view's `look-gap`s, or the ones of a class. */
function dividers(view: View, named = ""): HTMLElement[] {
  return [...view.renderRoot.querySelectorAll<HTMLElement>(`look-gap${named}`)];
}

/** A drag of one of a view's dividers, by its class, to a client point. */
async function drag(shell: TcApp, view: View, named: string, to: Point): Promise<void> {
  view.getBoundingClientRect = () => BOX;
  const [divider] = dividers(view, `.${named}`);
  for (const name of ["pointerdown", "pointermove", "pointerup"] as const) {
    divider!.dispatchEvent(
      new PointerEvent(name, { button: 0, bubbles: true, clientX: to.x, clientY: to.y }),
    );
  }
  await settled(shell);
}

/** The size a view asks its stylesheet for, `""` for the stylesheet's own. */
function size(view: View, property: string): string {
  return view.style.getPropertyValue(property);
}

/** The page a browser reloaded: the app taken down and stood up again. */
async function reloaded(): Promise<TcApp> {
  document.body.replaceChildren();
  return joined("edit");
}

beforeEach(() => {
  brokering();
  localStorage.clear();
});

afterEach(() => {
  unbrokered();
});

describe("the palette's divider", () => {
  it("leaves the palette its own width until it is dragged", async () => {
    expect(size(editing(await joined("edit")), "--palette-size")).toBe("");
  });

  it("sets the palette's width to where it was dragged", async () => {
    const shell = await joined("edit");

    await drag(shell, editing(shell), "palette", { x: 350, y: 300 });

    expect(size(editing(shell), "--palette-size")).toBe("300px");
  });

  /** The greatest leaves the drawing 256 px of the view's 1000, with the
   *  netlist shut. */
  it("holds the palette's width to a least and a greatest", async () => {
    const shell = await joined("edit");

    await drag(shell, editing(shell), "palette", { x: 60, y: 300 });
    expect(size(editing(shell), "--palette-size")).toBe("144px");

    await drag(shell, editing(shell), "palette", { x: 1040, y: 300 });
    expect(size(editing(shell), "--palette-size")).toBe("744px");
  });

  it("comes back where it was left after a reload", async () => {
    const shell = await joined("edit");
    await drag(shell, editing(shell), "palette", { x: 350, y: 300 });

    expect(size(editing(await reloaded()), "--palette-size")).toBe("300px");
    expect(localStorage.getItem("tc49.palette")).toBe("300");
  });

  it("does not move the run view's pane", async () => {
    const shell = await joined("edit");

    await drag(shell, editing(shell), "palette", { x: 350, y: 300 });

    expect(size(running(shell), "--pane-size")).toBe("");
    expect(size(running(await reloaded()), "--pane-size")).toBe("");
  });

  /** The canvas follows its own box. The suite states a box of another
   *  shape, and the view box stays as it was. */
  it("does not fit the drawing again", async () => {
    const shell = await joined("edit");
    const canvas = editing(shell).renderRoot.querySelector<TcCanvas>("tc-canvas")!;
    const viewed = (): string => canvas.renderRoot.querySelector("svg")!.getAttribute("viewBox")!;
    const before = viewed();
    canvas.getBoundingClientRect = () => ({ width: 400, height: 800 }) as DOMRect;

    await drag(shell, editing(shell), "palette", { x: 350, y: 300 });

    expect(viewed()).toBe(before);
  });
});

describe("the netlist's divider", () => {
  it("is there only while the netlist is open", async () => {
    const shell = await joined("edit");
    expect(dividers(editing(shell))).toHaveLength(1);

    await pressed(shell, "netlist");
    expect(dividers(editing(shell))).toHaveLength(2);

    await pressed(shell, "netlist");
    expect(dividers(editing(shell))).toHaveLength(1);
  });

  it("sets the netlist's width, measured from the view's right edge", async () => {
    const shell = await joined("edit");
    await pressed(shell, "netlist");

    await drag(shell, editing(shell), "netlist", { x: 700, y: 300 });

    expect(size(editing(shell), "--netlist-size")).toBe("350px");
    expect(size(editing(shell), "--palette-size")).toBe("");
  });

  /** The greatest the view hands over is 256 px short of the view's 1000.
   *  The stylesheet holds it against the palette as well. */
  it("holds the netlist's width to a least and a greatest", async () => {
    const shell = await joined("edit");
    await pressed(shell, "netlist");

    await drag(shell, editing(shell), "netlist", { x: 1040, y: 300 });
    expect(size(editing(shell), "--netlist-size")).toBe("192px");

    await drag(shell, editing(shell), "netlist", { x: 60, y: 300 });
    expect(size(editing(shell), "--netlist-size")).toBe("744px");
  });

  it("comes back where it was left after a reload", async () => {
    const shell = await joined("edit");
    await pressed(shell, "netlist");
    await drag(shell, editing(shell), "netlist", { x: 700, y: 300 });

    expect(size(editing(await reloaded()), "--netlist-size")).toBe("350px");
    expect(localStorage.getItem("tc49.netlist")).toBe("350");
    expect(localStorage.getItem("tc49.palette")).toBeNull();
  });
});

/**
 * The stock view's two boxes have 16 px left of the list, between the two
 * and right of the editor. The divider is the space between them, and the
 * point it is dragged to is its middle.
 */
describe("the stock view's divider", () => {
  it("leaves the list its own width until it is dragged", async () => {
    expect(size(stocking(await joined("stock")), "--list-size")).toBe("");
  });

  it("sets the list box's width to where it was dragged", async () => {
    const shell = await joined("stock");

    await drag(shell, stocking(shell), "divider", { x: 474, y: 300 });

    expect(size(stocking(shell), "--list-size")).toBe("400px");
  });

  /** The greatest leaves the editor box 320 px of the view's 1000, less
   *  the three spaces. */
  it("holds the list box's width to a least and a greatest", async () => {
    const shell = await joined("stock");

    await drag(shell, stocking(shell), "divider", { x: 60, y: 300 });
    expect(size(stocking(shell), "--list-size")).toBe("300px");

    await drag(shell, stocking(shell), "divider", { x: 1040, y: 300 });
    expect(size(stocking(shell), "--list-size")).toBe("632px");
  });

  it("comes back where it was left after a reload", async () => {
    const shell = await joined("stock");
    await drag(shell, stocking(shell), "divider", { x: 474, y: 300 });

    expect(size(stocking(await reloaded()), "--list-size")).toBe("400px");
    expect(localStorage.getItem("tc49.stock")).toBe("400");
  });
});
