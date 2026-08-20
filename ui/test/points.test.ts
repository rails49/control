// @vitest-environment happy-dom

/**
 * What a point drawn in a position looks like (CONTEXT.md, ui/PANEL.md, #98).
 *
 * A DOM test because the position is classes on rendered strokes: the road a
 * point does not currently offer is drawn faint, and which strokes those are
 * is the library's leg-to-position table read against the artwork's roads.
 * Neither is visible in the template's strings.
 */

import { render, svg } from "lit";
import { describe, expect, it } from "vitest";

import type { SymbolSpec } from "../src/model/drawing.js";
import type { Position } from "../src/symbols.generated.js";
import { artwork } from "../src/render/artwork.js";

/** The classes of every stroke the symbol draws, in the order drawn. */
function strokes(kind: SymbolSpec["kind"], position?: Position): string[] {
  const root = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  render(
    svg`${artwork({ kind } as SymbolSpec, undefined, undefined, undefined, position)}`,
    root,
  );
  return [...root.querySelectorAll("path")].map(
    (path) => path.getAttribute("class")!,
  );
}

describe("a point drawn in a position", () => {
  it("marks the road it does not offer, and only that one", () => {
    // A turnout's legs are named for its positions: lying closed it offers
    // the straight road, and the diverging one is set against.
    expect(strokes("turnout", "closed")).toEqual(["track", "track against"]);
    expect(strokes("turnout", "thrown")).toEqual(["track against", "track"]);
  });

  it("keeps a stroke a leg of either position runs over", () => {
    // A slip's two roads meet at the frog, so each half-stroke carries a
    // closed leg and a thrown one and is on the way whichever way the point
    // lies. The tick is the one stroke that is the slip road alone.
    const closed = strokes("single_slip", "closed");
    expect(closed.filter((one) => one === "track")).toHaveLength(4);
    expect(closed.filter((one) => one === "tick against")).toHaveLength(1);
    expect(strokes("double_slip", "thrown")).toEqual([
      "track",
      "track",
      "track",
      "track",
      "tick",
      "tick",
    ]);
  });

  it("draws every road plainly where nothing has commanded it", () => {
    // Which is the editor, and a palette tile, and a panel before the first
    // alignment: a drawing says what a point is, never where it lies.
    expect(strokes("turnout")).toEqual(["track", "track"]);
    expect(strokes("double_slip")).toEqual([
      "track",
      "track",
      "track",
      "track",
      "tick",
      "tick",
    ]);
  });

  it("leaves a symbol with no motor alone", () => {
    // A fixed crossing has nothing to command, so no address ever names it
    // and no position can reach it.
    expect(strokes("crossing", "thrown")).toEqual([
      "track",
      "track",
      "track",
      "track",
    ]);
  });
});
