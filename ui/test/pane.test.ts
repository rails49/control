// @vitest-environment happy-dom

/**
 * The run view's pane and the two gaps a person drags: between the pane and
 * the drawing ([#1344](https://github.com/rails49/control/issues/1344)), and
 * between the trains and the timetable
 * ([#1391](https://github.com/rails49/control/issues/1391)).
 *
 * happy-dom lays nothing out, so the suite states the view's box and reads
 * the sizes the view hands its stylesheet, `--pane-size` and `--lists-size`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/ui/tc-app.js";
import type { Point } from "../src/model/geometry.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import { running, settled, surface } from "./support/shell.js";
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

/** The view's two gaps: between the pane and the drawing, and between the
 *  trains and the timetable. */
type Gap = "pane" | "lists";

function divider(shell: TcApp, gap: Gap): HTMLElement {
  return running(shell).renderRoot.querySelector<HTMLElement>(`look-gap.${gap}`)!;
}

/** The size the view asks its stylesheet for, `""` for the stylesheet's own:
 *  the pane's, or the trains list's. */
function size(shell: TcApp, gap: Gap = "pane"): string {
  return running(shell).style.getPropertyValue(`--${gap}-size`);
}

/** A drag of a gap from where it is to a client point. */
async function drag(shell: TcApp, to: Point, gap: Gap = "pane"): Promise<void> {
  running(shell).getBoundingClientRect = () => BOX;
  for (const name of ["pointerdown", "pointermove", "pointerup"] as const) {
    divider(shell, gap).dispatchEvent(
      new PointerEvent(name, { button: 0, bubbles: true, clientX: to.x, clientY: to.y }),
    );
  }
  await settled(shell);
}

/** The page a browser reloaded: the app taken down and stood up again. */
async function reloaded(): Promise<TcApp> {
  document.body.replaceChildren();
  return joined();
}

/** The page given a width and a height, through happy-dom's own handle on
 *  its window. */
function paged(width: number, height: number): void {
  const page = window as unknown as {
    happyDOM: { setViewport(to: { width: number; height: number }): void };
  };
  page.happyDOM.setViewport({ width, height });
}

/** The page at a width and a height, as turning a tablet leaves it. */
async function turned(shell: TcApp, width: number, height: number): Promise<void> {
  paged(width, height);
  await settled(shell);
}

/** The height of the drawing's view box over its width. */
function shape(shell: TcApp): number {
  const [, , w, h] = surface(shell).getAttribute("viewBox")!.split(" ").map(Number);
  return h! / w!;
}

describe("the run view's divider", () => {
  beforeEach(() => {
    brokering();
    localStorage.clear();
  });

  afterEach(() => {
    unbrokered();
    paged(1024, 768);
  });

  it("sets the pane's width to where it was dragged", async () => {
    const shell = await joined();
    expect(size(shell)).toBe("");

    await drag(shell, { x: 350, y: 300 });

    expect(size(shell)).toBe("300px");
  });

  /** The least is where the roster is still usable, 144 px, and the
   *  greatest leaves the drawing 256 px of the view's 1000. */
  it("holds the pane's width to a least and a greatest", async () => {
    const shell = await joined();

    await drag(shell, { x: 60, y: 300 });
    expect(size(shell)).toBe("144px");

    await drag(shell, { x: 1040, y: 300 });
    expect(size(shell)).toBe("744px");
  });

  /** Above the drawing the greatest leaves it 192 px of the view's 700. */
  it("holds the pane's height to a least and a greatest", async () => {
    const shell = await joined();
    await turned(shell, 768, 1024);

    await drag(shell, { x: 400, y: 50 });
    expect(size(shell)).toBe("144px");

    await drag(shell, { x: 400, y: 730 });
    expect(size(shell)).toBe("508px");
  });

  it("comes back where it was left after a reload", async () => {
    await drag(await joined(), { x: 350, y: 300 });

    expect(size(await reloaded())).toBe("300px");
  });

  it("comes back where it was left after a reload on a page taller than it is wide", async () => {
    paged(768, 1024);
    await drag(await joined(), { x: 400, y: 240 });

    expect(size(await reloaded())).toBe("200px");
  });

  /** The pane is above the drawing there, so the divider sets its height,
   *  measured from the top of the view. */
  it("sets the pane's height on a page taller than it is wide", async () => {
    const shell = await joined();
    await turned(shell, 768, 1024);

    await drag(shell, { x: 400, y: 240 });

    expect(size(shell)).toBe("200px");
  });

  /** The size a browser kept for the pane when it was below the drawing is
   *  not read: the arrangement is above it now. */
  it("reads no size kept for the pane below the drawing", async () => {
    localStorage.setItem("tc49.pane.below", "300");
    paged(768, 1024);

    expect(size(await joined())).toBe("");
  });

  it("keeps one position for each arrangement", async () => {
    const shell = await joined();
    await drag(shell, { x: 350, y: 300 });
    await turned(shell, 768, 1024);
    expect(size(shell)).toBe("");
    await drag(shell, { x: 400, y: 240 });

    await turned(shell, 1024, 768);
    expect(size(shell)).toBe("300px");
    await turned(shell, 768, 1024);
    expect(size(shell)).toBe("200px");
  });

  /** The drawing is fitted to the shape the canvas has once the pane has
   *  moved, which the suite states as the browser would lay it out. */
  it("fits the drawing again when the divider moves and when the page turns", async () => {
    const shell = await joined();
    const canvas = running(shell).renderRoot.querySelector<TcCanvas>("tc-canvas")!;
    const laid = (width: number, height: number): void => {
      canvas.getBoundingClientRect = () => ({ width, height }) as DOMRect;
    };

    laid(700, 700);
    await drag(shell, { x: 350, y: 300 });
    expect(shape(shell)).toBeCloseTo(1);

    laid(400, 800);
    await turned(shell, 768, 1024);
    expect(shape(shell)).toBeCloseTo(2);
  });
});

/** A browser that refuses the store throws on every read and write of it
 *  (#1414). */
describe("the run view's divider in a browser that refuses the store", () => {
  beforeEach(() => {
    brokering();
    vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new DOMException("refused", "SecurityError");
    });
    vi.spyOn(localStorage, "setItem").mockImplementation(() => {
      throw new DOMException("refused", "SecurityError");
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    unbrokered();
  });

  it("comes onto the page and sets the pane's size when dragged", async () => {
    const shell = await joined();
    expect(running(shell)).not.toBeNull();

    await drag(shell, { x: 350, y: 300 });

    expect(size(shell)).toBe("300px");
  });
});

/**
 * The gap between the trains and the timetable (#1391). With the pane left
 * of the drawing the lists are one above the other and the gap sets the
 * trains list's height; with the pane above it they are side by side and it
 * sets the trains list's width. The pane spans the view's height in the one
 * arrangement and its width in the other, so the view's box is the lists'
 * box along the way the gap is dragged.
 */
describe("the gap between the trains and the timetable", () => {
  beforeEach(() => {
    brokering();
    localStorage.clear();
  });

  afterEach(() => {
    unbrokered();
    paged(1024, 768);
  });

  it("leaves the trains list its own size until it is dragged", async () => {
    expect(size(await joined(), "lists")).toBe("");
    paged(768, 1024);
    expect(size(await reloaded(), "lists")).toBe("");
  });

  it("sets the trains list's height to where it was dragged", async () => {
    const shell = await joined();

    await drag(shell, { x: 200, y: 340 }, "lists");

    expect(size(shell, "lists")).toBe("300px");
    expect(size(shell)).toBe("");
  });

  /** Each list keeps 96 px of the view's 700, less the 6 px gap. */
  it("holds the trains list's height so that each list keeps its least", async () => {
    const shell = await joined();

    await drag(shell, { x: 200, y: 50 }, "lists");
    expect(size(shell, "lists")).toBe("96px");

    await drag(shell, { x: 200, y: 730 }, "lists");
    expect(size(shell, "lists")).toBe("598px");
  });

  it("sets the trains list's width on a page taller than it is wide", async () => {
    const shell = await joined();
    await turned(shell, 768, 1024);

    await drag(shell, { x: 350, y: 100 }, "lists");

    expect(size(shell, "lists")).toBe("300px");
  });

  /** Side by side each list keeps 144 px of the view's 1000, less the gap. */
  it("holds the trains list's width so that each list keeps its least", async () => {
    const shell = await joined();
    await turned(shell, 768, 1024);

    await drag(shell, { x: 60, y: 100 }, "lists");
    expect(size(shell, "lists")).toBe("144px");

    await drag(shell, { x: 1040, y: 100 }, "lists");
    expect(size(shell, "lists")).toBe("850px");
  });

  it("keeps one position for each arrangement, and a reload brings it back", async () => {
    const shell = await joined();
    await drag(shell, { x: 200, y: 340 }, "lists");
    await turned(shell, 768, 1024);
    expect(size(shell, "lists")).toBe("");
    await drag(shell, { x: 450, y: 100 }, "lists");

    await turned(shell, 1024, 768);
    expect(size(shell, "lists")).toBe("300px");
    expect(size(await reloaded(), "lists")).toBe("300px");
    paged(768, 1024);
    expect(size(await reloaded(), "lists")).toBe("400px");
  });

  it("is kept under a key of its own", async () => {
    await drag(await joined(), { x: 200, y: 340 }, "lists");

    expect(localStorage.getItem("tc49.lists.left")).toBe("300");
    expect(localStorage.getItem("tc49.pane.left")).toBeNull();
  });

  it("fits the drawing again when it moves", async () => {
    const shell = await joined();
    const canvas = running(shell).renderRoot.querySelector<TcCanvas>("tc-canvas")!;
    canvas.getBoundingClientRect = () => ({ width: 400, height: 800 }) as DOMRect;

    await drag(shell, { x: 200, y: 340 }, "lists");

    expect(shape(shell)).toBeCloseTo(2);
  });

  /** Turning the page under a drag ends it: a move after the turn sets
   *  nothing. */
  it("is let go when the page turns", async () => {
    const shell = await joined();
    running(shell).getBoundingClientRect = () => BOX;
    const gap = divider(shell, "lists");
    gap.dispatchEvent(new PointerEvent("pointerdown", { button: 0, clientX: 200, clientY: 340 }));
    await turned(shell, 768, 1024);
    gap.dispatchEvent(new PointerEvent("pointermove", { clientX: 350, clientY: 100 }));
    await settled(shell);

    expect(size(shell, "lists")).toBe("");
  });
});
