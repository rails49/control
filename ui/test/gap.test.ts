// @vitest-environment happy-dom

/**
 * `tc-gap`, the gap a person drags between two parts of the run view
 * ([#1391](https://github.com/rails49/control/issues/1391)). It takes the
 * press and the drag and raises the pointer's client point while dragged.
 * What size that point means is the view's.
 */

import { afterEach, describe, expect, it } from "vitest";

import type { Point } from "../src/model/geometry.js";
import "../src/ui/tc-gap.js";
import type { TcGap } from "../src/ui/tc-gap.js";

async function made(axis: "x" | "y" = "x"): Promise<{ gap: TcGap; moved: Point[] }> {
  const gap = document.createElement("tc-gap");
  gap.axis = axis;
  const moved: Point[] = [];
  gap.addEventListener("gap-moved", (event) => moved.push((event as CustomEvent<Point>).detail));
  document.body.append(gap);
  await gap.updateComplete;
  return { gap, moved };
}

function pointer(gap: TcGap, name: string, x: number, y: number, button = 0): void {
  gap.dispatchEvent(new PointerEvent(name, { button, bubbles: true, clientX: x, clientY: y }));
}

describe("the gap", () => {
  afterEach(() => document.body.replaceChildren());

  it("raises the pointer's client point while dragged", async () => {
    const { gap, moved } = await made();
    pointer(gap, "pointerdown", 10, 20);
    pointer(gap, "pointermove", 30, 40);
    pointer(gap, "pointermove", 50, 60);

    expect(moved).toEqual([
      { x: 30, y: 40 },
      { x: 50, y: 60 },
    ]);
  });

  it("raises nothing for a pointer moving over it unpressed", async () => {
    const { gap, moved } = await made();
    pointer(gap, "pointermove", 30, 40);

    expect(moved).toEqual([]);
  });

  it("is not dragged by a button other than the first", async () => {
    const { gap, moved } = await made();
    pointer(gap, "pointerdown", 10, 20, 2);
    pointer(gap, "pointermove", 30, 40);

    expect(moved).toEqual([]);
  });

  it.each(["pointerup", "pointercancel"])("is let go by a %s", async (name) => {
    const { gap, moved } = await made();
    pointer(gap, "pointerdown", 10, 20);
    pointer(gap, name, 10, 20);
    pointer(gap, "pointermove", 30, 40);

    expect(moved).toEqual([]);
  });

  /** The page turned under a drag: the gap is the other way round now, and
   *  the drag ends. */
  it("is let go when it turns the other way", async () => {
    const { gap, moved } = await made("x");
    pointer(gap, "pointerdown", 10, 20);
    gap.axis = "y";
    await gap.updateComplete;
    pointer(gap, "pointermove", 30, 40);

    expect(moved).toEqual([]);
  });

  it("names the way it is dragged on its element, for its stylesheet", async () => {
    const { gap } = await made("y");

    expect(gap.getAttribute("axis")).toBe("y");
  });
});
