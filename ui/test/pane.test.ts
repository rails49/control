// @vitest-environment happy-dom

/**
 * The run view's pane and the divider a person drags
 * ([#1344](https://github.com/rails49/control/issues/1344)).
 *
 * happy-dom lays nothing out, so the suite states the view's box and reads
 * the size the view hands its stylesheet, `--pane-size`.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

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

function divider(shell: TcApp): HTMLElement {
  return running(shell).renderRoot.querySelector<HTMLElement>(".divider")!;
}

/** The size the view asks its stylesheet for, `""` for the stylesheet's own. */
function size(shell: TcApp): string {
  return running(shell).style.getPropertyValue("--pane-size");
}

/** A drag of the divider from where it is to a client point. */
async function drag(shell: TcApp, to: Point): Promise<void> {
  running(shell).getBoundingClientRect = () => BOX;
  for (const name of ["pointerdown", "pointermove", "pointerup"] as const) {
    divider(shell).dispatchEvent(
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
