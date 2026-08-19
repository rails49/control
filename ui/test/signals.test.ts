// @vitest-environment happy-dom

/**
 * What a signal draws and what an aspect lights (ui/EDITOR.md#symbol-geometry,
 * ADR-0025).
 *
 * A DOM test because both are positions and classes on rendered elements: the
 * lamp order is the geometry itself, and an aspect is a class on the signal's
 * group that a stylesheet turns into a set of lit lamps. Neither is visible in
 * the template's strings.
 */

import { render, svg } from "lit";
import { describe, expect, it } from "vitest";

import type { SymbolSpec } from "../src/model/drawing.js";
import { PINS } from "../src/symbols.generated.js";
import { artwork, type Aspect } from "../src/render/artwork.js";

function drawn(aspects?: ReadonlyMap<string, Aspect>): SVGSVGElement {
  const root = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  render(
    svg`${artwork({ kind: "block" } as SymbolSpec, undefined, undefined, aspects)}`,
    root,
  );
  return root;
}

/** Each lamp's centre along the plaque, in the signal group at `end`. */
function lamps(root: SVGSVGElement, end: "A" | "B"): Record<string, number> {
  const group = root.querySelector(`.signal.end-${end}`)!;
  return Object.fromEntries(
    [...group.querySelectorAll("circle.lamp")].map((lamp) => [
      lamp.getAttribute("class")!.replace("lamp ", ""),
      Number(lamp.getAttribute("cx")),
    ]),
  );
}

describe("a signal's lamps", () => {
  it("orders them by distance from the block's rectangle", () => {
    // The block's rectangle spans the middle of the symbol, so at the A end
    // outward is to the left and at the B end outward is to the right. Green
    // is furthest out at both, amber nearest, which is what keeps the pair
    // point symmetric under a rotation or a flip.
    const root = drawn();
    const a = lamps(root, "A");
    const b = lamps(root, "B");

    expect(a.green).toBeLessThan(a.red);
    expect(a.red).toBeLessThan(a.amber);
    expect(b.amber).toBeLessThan(b.red);
    expect(b.red).toBeLessThan(b.green);
  });

  it("spaces them evenly, so no lamp reads as the odd one", () => {
    const a = lamps(drawn(), "A");
    expect(a.red - a.green).toBeCloseTo(a.amber - a.red);
  });

  it("keeps every lamp inside the plaque", () => {
    const root = drawn();
    const plaque = root.querySelector(".signal.end-A .plaque")!;
    const box = plaque.getAttribute("d")!;
    const xs = [...box.matchAll(/[-0-9.]+/g)]
      .map(Number)
      .filter((_, i) => i % 2 === 0);
    const a = lamps(root, "A");
    expect(Math.min(...Object.values(a))).toBeGreaterThan(Math.min(...xs));
    expect(Math.max(...Object.values(a))).toBeLessThan(Math.max(...xs));
  });
});

describe("an aspect", () => {
  it("is a class on the signal's group, not on a lamp", () => {
    const root = drawn(new Map([["A", "approach"]]));
    expect(root.querySelector(".signal.end-A")!.classList).toContain("approach");
    // The lamps stay named for their colours whatever is showing: an aspect
    // is a set of lit lamps, so no lamp can carry the aspect's name.
    const classes = [...root.querySelectorAll(".signal.end-A circle.lamp")].map(
      (lamp) => lamp.getAttribute("class"),
    );
    expect(classes).toEqual(["lamp green", "lamp red", "lamp amber"]);
  });

  it("leaves an unnamed end with no aspect at all, which is edit mode", () => {
    const root = drawn(new Map([["A", "clear"]]));
    const b = root.querySelector(".signal.end-B")!;
    for (const aspect of ["stop", "approach", "clear"]) {
      expect(b.classList).not.toContain(aspect);
    }
  });

  it("names each end independently", () => {
    const root = drawn(
      new Map<string, Aspect>([
        ["A", "stop"],
        ["B", "clear"],
      ]),
    );
    expect(root.querySelector(".signal.end-A")!.classList).toContain("stop");
    expect(root.querySelector(".signal.end-B")!.classList).toContain("clear");
  });
});

describe("an aspect's name", () => {
  /** Every class the artwork puts on an element, across every symbol kind. */
  function drawnClasses(): Set<string> {
    const found = new Set<string>();
    for (const kind of Object.keys(PINS) as (keyof typeof PINS)[]) {
      const root = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      render(svg`${artwork({ kind } as SymbolSpec)}`, root);
      for (const el of root.querySelectorAll("*")) {
        for (const one of el.classList) found.add(one);
      }
    }
    return found;
  }

  it("is not also the name of something the artwork draws", () => {
    // The aspect goes on the signal's group, so a rule matching its name is
    // inherited by the lamps inside it. `stop` once collided with the buffer
    // stop's class, whose stroke is over three times a lamp's radius, and
    // every lamp of every signal at stop was swallowed by it. Nothing in the
    // suite noticed: the classes were all correct and only the paint was
    // wrong, which is what a screenshot catches and a DOM assertion does not.
    const drawn = drawnClasses();
    for (const aspect of ["stop", "approach", "clear"]) {
      expect([...drawn]).not.toContain(aspect);
    }
  });
});
