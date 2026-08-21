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

import type { Drawing, SymbolSpec } from "../src/model/drawing.js";
import { anchorIn } from "../src/model/geometry.js";
import { Panel } from "../src/model/panel.js";
import { positionsBySymbol } from "../src/model/scene.js";
import type { Explained, Layout } from "../src/model/store.js";
import type { TraceEvent } from "../src/model/trace.js";
import { TRANSITS, type Position } from "../src/symbols.generated.js";
import { artwork } from "../src/render/artwork.js";
import { panelStyles } from "../src/ui/tc-panel.styles.js";

/** Every stroke the symbol draws, in the order drawn. */
function drawn(
  kind: SymbolSpec["kind"],
  position?: Position,
): SVGPathElement[] {
  const root = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  render(
    svg`${artwork({ kind } as SymbolSpec, undefined, undefined, undefined, position)}`,
    root,
  );
  return [...root.querySelectorAll("path")];
}

/** The classes of every stroke the symbol draws, in the order drawn. */
function strokes(kind: SymbolSpec["kind"], position?: Position): string[] {
  return drawn(kind, position).map((path) => path.getAttribute("class")!);
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

/**
 * The panel's whole alignment path, end to end (#130): the address-and-position
 * pairs `align` carries, the address-keyed ledger they populate, the drawing
 * that turns an address back into a symbol, and the class the artwork puts on
 * the road the point does not offer.
 *
 * Each seam is checked on its own elsewhere — `panel.test.ts` for the ledger,
 * `scene.test.ts` for the drawing's lookup, the tests above for the classes —
 * and each stayed green while the styling reached nothing, because no scenario
 * drove a drawing whose points carry addresses. So the path is walked here in
 * one piece, with the alignment `gotthard/positions` produces.
 */

/** j1 of `gotthard` in miniature: sw1 and sw2 share address 5 and move
 *  together, sw3 wears 6, and sw4 wears one the run never commands.
 *
 *  A transcription, this and the `align` below both: the four symbols are the
 *  committed drawing's and the command is what `gotthard/positions` really
 *  publishes at j1. No asset can be read from here — no YAML reaches the `ui`
 *  package — so `tests/system/test_positions.py` holds a mirror of what the
 *  two encode and fails when either original moves. Change one, change the
 *  other. */
const YARD: Drawing = {
  drawing: "yard",
  symbols: {
    sw1: { kind: "turnout", at: [15, 4], addr: "5" },
    sw2: { kind: "turnout", at: [15, 3], addr: "5" },
    sw3: { kind: "turnout", at: [14, 5], addr: "6" },
    sw4: { kind: "turnout", at: [24, 4], addr: "7" },
  },
  wires: [],
};

/** The panel holds a layout to read block states off; an alignment needs
 *  nothing from it, so the toy railroad here is an empty one. */
const NOTHING: Layout = { layout: "yard", blocks: {}, connections: {} };
const UNEXPLAINED: Explained = { layout: "yard", connections: {} };

/** An `align` as the dispatcher publishes it: the points one transit's way
 *  needs, by address (ADR-0022). */
function align(...points: [string, Position][]): Partial<TraceEvent> {
  return {
    event: "align",
    connection: "j1",
    transit: "A2_A__CE2_B",
    points: points.map(([addr, position]) => ({ addr, position })),
  };
}

/** Which of a turnout's legs the drawing shows set against, by name, after a
 *  run of alignments. The class carries no leg name and `roads` draws a lit
 *  stroke last, so the leg is read off where its stroke ends: every leg runs
 *  from the toe to the pin it is named for. */
function against(symbol: string, ...commands: Partial<TraceEvent>[]): string[] {
  const model = new Panel(NOTHING, UNEXPLAINED, []);
  for (const command of commands)
    model.apply({ boundary: 0, ...command } as TraceEvent);
  const position = positionsBySymbol(YARD, model.positionsByAddress()).get(
    symbol,
  );
  const roads = drawn("turnout", position);
  return Object.keys(TRANSITS.turnout).filter((leg) => {
    const at = anchorIn("turnout", leg);
    const stroke = roads.find((path) => {
      const d = path.getAttribute("d")!;
      const [x, y] = d.slice(d.lastIndexOf("L") + 1).split(" ").map(Number);
      return Math.abs(x - at.x) < 1e-9 && Math.abs(y - at.y) < 1e-9;
    })!;
    return stroke.classList.contains("against");
  });
}

describe("a point the alignment command has placed", () => {
  it("fades the road it does not offer, on both points on the address", () => {
    // What crossing j1 to reach A2 commands: address 5 closed and 6 thrown.
    // A turnout's legs are named for its positions, so lying closed it offers
    // the straight road and the diverging one is the road set against.
    const j1 = align(["1", "thrown"], ["5", "closed"], ["6", "thrown"]);
    expect(against("sw1", j1)).toEqual(["diverging"]);
    expect(against("sw2", j1)).toEqual(["diverging"]);
    expect(against("sw3", j1)).toEqual(["straight"]);
  });

  it("moves the fade to the other road when the alignment changes", () => {
    // The other way through the same junction, to A1, which wants address 5
    // thrown instead: the pair swap which of their roads is on offer. 6 is
    // thrown for either road, so sw3 does not move and its straight road
    // stays the faint one.
    const j1 = align(["1", "thrown"], ["5", "closed"], ["6", "thrown"]);
    const over = align(["1", "thrown"], ["5", "thrown"], ["6", "thrown"]);
    expect(against("sw1", j1, over)).toEqual(["straight"]);
    expect(against("sw2", j1, over)).toEqual(["straight"]);
    expect(against("sw3", j1, over)).toEqual(["straight"]);
  });

  it("leaves a point no command has named with both roads on offer", () => {
    // sw4 is on the far side of the station and this route never crosses it,
    // so nothing has said which way it lies and the panel says nothing either.
    expect(against("sw4", align(["5", "closed"]))).toEqual([]);
  });
});

describe("the fade itself", () => {
  it("is a rule in the sheet the panel paints with", () => {
    // The class is a fade only because a rule says so, and a sheet tidied of
    // that rule leaves every test above green with nothing faint on screen.
    // The opacity is #98's to choose; that it is below full is the language.
    const rules = [
      ...panelStyles.cssText
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .matchAll(/([^{}]*)\{([^{}]*)\}/g),
    ].filter(([, selector]) => selector.includes(".against"));
    expect(rules.length).toBeGreaterThan(0);
    for (const [, , declared] of rules) {
      const opacity = Number(/opacity:\s*([\d.]+)/.exec(declared)?.[1]);
      expect(opacity).toBeGreaterThan(0);
      expect(opacity).toBeLessThan(1);
    }
  });
});
