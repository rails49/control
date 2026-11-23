// @vitest-environment happy-dom

/**
 * What a point drawn in a position looks like (GLOSSARY.md, ui/PANEL.md, #98).
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
import { WHOLE } from "../src/model/inspect.js";
import { Panel } from "../src/model/panel.js";
import { positionsBySymbol } from "../src/model/scene.js";
import type { Explained, Layout } from "../src/model/store.js";
import type { TraceEvent } from "../src/model/trace.js";
import { TRANSITS, type Position } from "../src/symbols.generated.js";
import { artwork } from "../src/render/artwork.js";
import { canvasStyles } from "../src/ui/tc-canvas.styles.js";

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

/** A turnout's strokes by the leg each draws, read off where the stroke
 *  ends: every leg runs from the toe to the pin it is named for. */
function turnoutLegs(
  spec: SymbolSpec,
  lit?: ReadonlySet<string>,
  position?: Position,
): Map<string, SVGPathElement> {
  const root = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  render(svg`${artwork(spec, lit, undefined, undefined, position)}`, root);
  const roads = [...root.querySelectorAll("path")];
  return new Map(
    Object.keys(TRANSITS.turnout).map((leg) => {
      const at = anchorIn("turnout", leg, spec.rot);
      const stroke = roads.find((path) => {
        const [x, y] = ends(path)[1];
        return Math.abs(x! - at.x) < 1e-9 && Math.abs(y! - at.y) < 1e-9;
      })!;
      return [leg, stroke];
    }),
  );
}

/** The points a stroke's path names, in order: its ends, and for a curve the
 *  two ends of the curve and its control point between them. */
function points(path: SVGPathElement): number[][] {
  const numbers = path.getAttribute("d")!.match(/-?\d+(\.\d+)?/g)!.map(Number);
  return numbers.flatMap((x, i) => (i % 2 === 0 ? [[x, numbers[i + 1]!]] : []));
}

/** Where a stroke starts and ends. */
function ends(path: SVGPathElement): [number[], number[]] {
  const all = points(path);
  return [all[0]!, all[all.length - 1]!];
}

/** Which of a turnout's legs are drawn set against, by name. */
function legsAgainst(spec: SymbolSpec, position: Position): string[] {
  return [...turnoutLegs(spec, undefined, position)]
    .filter(([, path]) => path.classList.contains("against"))
    .map(([leg]) => leg);
}

describe("a point drawn in a position", () => {
  it("marks the road it does not offer, and only that one", () => {
    // A turnout's legs are named for its positions: lying closed it offers
    // the straight road, and the diverging one is set against. The faint
    // road is drawn first, under the solid one.
    expect(strokes("turnout", "closed")).toEqual(["track against", "track"]);
    expect(strokes("turnout", "thrown")).toEqual(["track against", "track"]);
    for (const rot of [0, 45, 90, 315] as const) {
      const spec: SymbolSpec = { kind: "turnout", rot };
      expect(legsAgainst(spec, "closed")).toEqual(["diverging"]);
      expect(legsAgainst(spec, "thrown")).toEqual(["straight"]);
    }
  });

  it("draws a slip's roads solid and its through routes faint when thrown", () => {
    // Every leg is its own stroke (#1295): thrown, a double slip offers both
    // slip curves and neither through route, and closed the reverse.
    const curved = (kind: SymbolSpec["kind"], position: Position) =>
      drawn(kind, position).map(
        (path) =>
          `${path.getAttribute("d")!.includes("Q") ? "curve" : "straight"}${
            path.classList.contains("against") ? " against" : ""
          }`,
      );
    expect(curved("double_slip", "thrown")).toEqual([
      "straight against",
      "straight against",
      "curve",
      "curve",
    ]);
    expect(curved("double_slip", "closed")).toEqual([
      "curve against",
      "curve against",
      "straight",
      "straight",
    ]);
    expect(curved("single_slip", "closed")).toEqual([
      "curve against",
      "straight",
      "straight",
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
    ]);
  });

  it("leaves a symbol with no motor alone", () => {
    // A fixed crossing has nothing to command, so no address ever names it
    // and no position can reach it.
    expect(strokes("crossing", "thrown")).toEqual(["track", "track"]);
  });
});

describe("a turnout's legs", () => {
  /** The editor and the palette (nothing lit, no position), a lit way, and a
   *  run with the point lying either way. */
  const modes: [string, ReadonlySet<string> | undefined, Position | undefined][] = [
    ["the editor", undefined, undefined],
    ["a lit way", new Set([WHOLE]), undefined],
    ["a run, closed", undefined, "closed"],
    ["a run, thrown", undefined, "thrown"],
  ];

  for (const rot of [0, 45] as const) {
    it(`both start at the toe at rot ${rot}`, () => {
      const toe = anchorIn("turnout", "toe", rot);
      const spec: SymbolSpec = { kind: "turnout", rot };
      for (const [mode, lit, position] of modes) {
        for (const [leg, path] of turnoutLegs(spec, lit, position)) {
          expect(ends(path)[0], `${mode}, ${leg}`).toEqual([toe.x, toe.y]);
        }
      }
    });

    it(`the diverging road leaves in line and arrives at 45° at rot ${rot}`, () => {
      // The straight road is one straight stroke. The diverging road starts
      // along it and ends along the diverging pin's own direction, which is
      // 45° from the straight road's (#1295).
      const spec: SymbolSpec = { kind: "turnout", rot };
      const p = (pin: string) => anchorIn("turnout", pin, rot);
      const legs = turnoutLegs(spec);
      expect(points(legs.get("straight")!)).toEqual([
        [p("toe").x, p("toe").y],
        [p("straight").x, p("straight").y],
      ]);

      const [from, begin, frog, end, to] = points(legs.get("diverging")!);
      expect(from).toEqual([p("toe").x, p("toe").y]);
      expect(to).toEqual([p("diverging").x, p("diverging").y]);
      expect(frog).toEqual([1, 0.5]);
      // A quadratic curve leaves along the line to its control point and
      // arrives along the line from it.
      const heading = (a: number[], b: number[]) =>
        (Math.round((Math.atan2(b[1]! - a[1]!, b[0]! - a[0]!) * 180) / Math.PI) + 360) % 360;
      const straight = heading([p("toe").x, p("toe").y], [p("straight").x, p("straight").y]);
      expect(straight).toBe(rot);
      expect(heading(begin!, frog!)).toBe(straight);
      expect(heading(frog!, end!)).toBe((straight + 315) % 360);
      expect(heading(frog!, to!)).toBe((straight + 315) % 360);
    });
  }
});

/**
 * The panel's whole alignment path, end to end (#130): the address-and-position
 * pairs `align` carries, as the `wanted/point` rows `layout` writes for them
 * (#666), the address-keyed ledger they populate, the drawing
 * that turns an address back into a symbol, and the class the artwork puts on
 * the road the point does not offer.
 *
 * Each seam is checked on its own elsewhere — `panel.test.ts` for the ledger,
 * `scene.test.ts` for the drawing's lookup, the tests above for the classes —
 * and each stayed green while the styling reached nothing, because no scenario
 * drove a drawing whose points carry addresses. So the path is walked here in
 * one piece, with the alignment `reversing-loops/positions` produces.
 */

/** j1 of `reversing-loops` in miniature: sw1 and sw2 share address `101` and
 *  move together, sw3 wears `102`, and sw4 wears one the run never commands.
 *  An address names no system and is the string the hardware answers to
 *  (ADR-0059); the panel keys its ledger by the whole of it and reads no part
 *  of it apart.
 *
 *  A transcription, this and the `align` below both: the four symbols are the
 *  committed drawing's and the command is what `reversing-loops/positions` really
 *  publishes at j1. No asset can be read from here — no YAML reaches the `ui`
 *  package — so `tests/system/test_positions.py` holds a mirror of what the
 *  two encode and fails when either original moves. Change one, change the
 *  other. */
const YARD: Drawing = {
  drawing: "yard",
  symbols: {
    sw1: { kind: "turnout", at: [15, 4], addr: "101" },
    sw2: { kind: "turnout", at: [15, 3], addr: "101" },
    sw3: { kind: "turnout", at: [14, 5], addr: "102" },
    sw4: { kind: "turnout", at: [24, 4], addr: "103" },
  },
  wires: [],
};

/** The panel holds a layout to read block states off; an alignment needs
 *  nothing from it, so the toy railroad here is an empty one. */
const NOTHING: Layout = { layout: "yard", blocks: {}, connections: {} };
const UNEXPLAINED: Explained = { layout: "yard", connections: {} };

/** What `layout` writes for an `align` as the dispatcher publishes it: one
 *  retained `wanted/point` row for each point the transit's way needs, by
 *  address (ADR-0022, ADR-0068). The panel reads the rows and never the
 *  command. */
function align(...points: [string, Position][]): Partial<TraceEvent>[] {
  return points.map(([addr, position]) => ({
    event: "wanted/point",
    addr,
    position,
  }));
}

/** Which of a turnout's legs the drawing shows set against, by name, after a
 *  run of alignments. The class carries no leg name and `roads` draws a lit
 *  stroke last, so the leg is read off where its stroke ends: every leg runs
 *  from the toe to the pin it is named for. */
function against(symbol: string, ...commands: Partial<TraceEvent>[][]): string[] {
  const model = new Panel(NOTHING, UNEXPLAINED, []);
  for (const row of commands.flat()) model.apply({ ...row } as TraceEvent);
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
    // What crossing j1 to reach A2 commands: `101` closed and `102` thrown.
    // A turnout's legs are named for its positions, so lying closed it offers
    // the straight road and the diverging one is the road set against.
    const j1 = align(
      ["105", "thrown"],
      ["101", "closed"],
      ["102", "thrown"],
    );
    expect(against("sw1", j1)).toEqual(["diverging"]);
    expect(against("sw2", j1)).toEqual(["diverging"]);
    expect(against("sw3", j1)).toEqual(["straight"]);
  });

  it("moves the fade to the other road when the alignment changes", () => {
    // The other way through the same junction, to A1, which wants `101`
    // thrown instead: the pair swap which of their roads is on offer.
    // `102` is thrown for either road, so sw3 does not move and its
    // straight road stays the faint one.
    const j1 = align(
      ["105", "thrown"],
      ["101", "closed"],
      ["102", "thrown"],
    );
    const over = align(
      ["105", "thrown"],
      ["101", "thrown"],
      ["102", "thrown"],
    );
    expect(against("sw1", j1, over)).toEqual(["straight"]);
    expect(against("sw2", j1, over)).toEqual(["straight"]);
    expect(against("sw3", j1, over)).toEqual(["straight"]);
  });

  it("leaves a point no command has named with both roads on offer", () => {
    // sw4 is on the far side of the station and this route never crosses it,
    // so nothing has said which way it lies and the panel says nothing either.
    expect(against("sw4", align(["101", "closed"]))).toEqual([]);
  });
});

describe("the fade itself", () => {
  it("is a rule in the sheet the panel paints with", () => {
    // The class is a fade only because a rule says so, and a sheet tidied of
    // that rule leaves every test above green with nothing faint on screen.
    // The opacity is #98's to choose; that it is below full is the language.
    const rules = [
      ...canvasStyles.cssText
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
