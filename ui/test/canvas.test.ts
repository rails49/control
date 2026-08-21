// @vitest-environment happy-dom

/**
 * The one thing the canvas draws that only `/review` can know: the label a
 * portal pairing with nothing wears (EDITOR.md#symbol-geometry).
 *
 * A DOM test because the whole of it is what the component renders, and
 * because what it renders rests on a contract with the store — that
 * `unpaired_portals` names symbols and not pins. A test at the model seam
 * cannot see that mismatch: the map would be keyed by `p1.P`, no symbol would
 * ever match, and nothing would be drawn while every test stayed green.
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-canvas.js";
import type { Drawing } from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import type { Chosen } from "../src/model/inspect.js";
import type { Review, Transit, UnpairedPortal } from "../src/model/store.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";

/**
 * A pair, both halves wearing `p1`, their mouths facing outwards at either end
 * of the sheet — track that vanishes west and continues east, which is what a
 * portal pair is for.
 */
const DRAWING: Drawing = {
  drawing: "two-portals",
  symbols: {
    p1: { kind: "portal", at: [0, 0], rot: 180, label: "p1" },
    p2: { kind: "portal", at: [10, 0], label: "p1" },
  },
  wires: [],
};

function reviewed(unpaired: UnpairedPortal[]): Review {
  return {
    red_pins: [],
    unpaired_portals: unpaired,
    junctions: [],
    joints: [],
    motor_faults: [],
    layout: null,
    explain: null,
    refused: null,
    offending: [],
  };
}

async function canvasOf(unpaired: UnpairedPortal[]) {
  const canvas = document.createElement("tc-canvas");
  canvas.editor = new Editor(structuredClone(DRAWING));
  canvas.review = reviewed(unpaired);
  document.body.append(canvas);
  await canvas.updateComplete;
  return canvas;
}

/** The marks the canvas draws, each as its text, where it sits and which end
 *  of it sits there. */
async function marks(
  unpaired: UnpairedPortal[],
): Promise<{ label: string; x: number; anchor: string }[]> {
  const canvas = await canvasOf(unpaired);
  const found = [...canvas.renderRoot.querySelectorAll("text.unpaired")].map(
    (text) => ({
      label: text.textContent!.trim(),
      x: Number(text.getAttribute("x")),
      anchor: text.getAttribute("text-anchor")!,
    }),
  );
  canvas.remove();
  return found;
}

describe("the label a portal pairing with nothing wears", () => {
  it("draws it on the portal the review names, keyed by symbol", async () => {
    const found = await marks([{ label: "p1", portals: ["p1"] }]);
    expect(found.map((one) => one.label)).toEqual(["p1"]);
    // p1 is turned, so its mouth and its label are west of where it sits.
    expect(found[0]!.x).toBeCloseTo(-0.2);
  });

  it("draws nothing where every label pairs", async () => {
    expect(await marks([])).toEqual([]);
  });

  it("marks every portal wearing a label that does not pair", async () => {
    const found = await marks([{ label: "p1", portals: ["p1", "p2"] }]);
    expect(found.map((one) => one.label)).toEqual(["p1", "p1"]);
  });

  it("runs the label away from the mouth, whichever way it points", async () => {
    // Centred text would run back over the artwork it marks as soon as the
    // label is more than a glyph or two, and which way is back depends on the
    // turn: the mark starts at the end nearest the mouth.
    const [west, east] = await marks([{ label: "p1", portals: ["p1", "p2"] }]);
    expect(west!.anchor).toBe("end");
    expect(east!.anchor).toBe("start");
    expect(east!.x).toBeCloseTo(11.2);
  });
});

describe("fitting the view", () => {
  it("keeps the marks on the sheet", async () => {
    // A portal's one pin is on the side away from its mouth, so the outermost
    // thing in the drawing can be the very mark that wants looking at: here
    // the pins span 1 to 10 and the two marks sit at -0.2 and 11.2.
    const canvas = await canvasOf([
      { label: "p1", portals: ["p1"] },
      { label: "p2", portals: ["p2"] },
    ]);
    canvas.fit();
    await canvas.updateComplete;
    const [x, , w] = canvas.renderRoot
      .querySelector("svg")!
      .getAttribute("viewBox")!
      .split(" ")
      .map(Number);
    expect(x!).toBeLessThanOrEqual(-0.2);
    expect(x! + w!).toBeGreaterThanOrEqual(11.2);
    canvas.remove();
  });
});

/**
 * What `File ▸ Export SVG…` writes (#86, model/export.ts).
 *
 * A DOM test because the clone is the one part of the export that needs a
 * document: what the file says around it is the model's and has its own test
 * with no DOM.
 */
describe("the drawing as a standalone file", () => {
  /** Two blocks and the wire between them, drawn well apart so the frame is
   *  plainly not the pane's shape. */
  const RAILROAD: Drawing = {
    drawing: "two-blocks",
    symbols: {
      west: { kind: "block", at: [0, 0], length: 1000 },
      east: { kind: "block", at: [6, 0], length: 1000 },
    },
    wires: [["west.B", "east.A"]],
  };

  async function drawn() {
    const canvas = document.createElement("tc-canvas");
    canvas.editor = new Editor(structuredClone(RAILROAD));
    canvas.review = reviewed([]);
    document.body.append(canvas);
    await canvas.updateComplete;
    return canvas;
  }

  it("frames the whole drawing wherever the canvas is looking", async () => {
    const canvas = await drawn();
    canvas.zoom(8);
    await canvas.updateComplete;
    const written = canvas.exported();
    const [x, y, w, h] = /viewBox="([^"]*)"/
      .exec(written)![1]!
      .split(" ")
      .map(Number);
    // The pins span 0 to 8 across and sit on the one row.
    expect(x!).toBeLessThanOrEqual(0);
    expect(x! + w!).toBeGreaterThanOrEqual(8);
    expect(y!).toBeLessThanOrEqual(0.5);
    expect(y! + h!).toBeGreaterThanOrEqual(0.5);
    // The sheet is drawn to the pane on screen, so it is redrawn to the frame.
    expect(written).toContain(
      `<rect class="sheet" x="${x}" y="${y}" width="${w}" height="${h}"`,
    );
    canvas.remove();
  });

  it("keeps what is on the sheet: the pins and the block names", async () => {
    const canvas = await drawn();
    const written = canvas.exported();
    expect(written).toContain('class="pin"');
    expect(written).toContain(">west</text>");
    expect(written).toContain(">east</text>");
    canvas.remove();
  });

  /** Lit leaves a marker between the parts of a template, and each carries a
   *  number minted per page load: left in, the same drawing would export
   *  differently every session. */
  it("leaves out lit's bookkeeping", async () => {
    const canvas = await drawn();
    expect(canvas.exported()).not.toContain("<!--");
    canvas.remove();
  });

  /** A gesture in progress is not the drawing, so the same drawing gives the
   *  same bytes whether or not one is under way. */
  it("leaves out a selection and a wire in flight", async () => {
    const canvas = await drawn();
    const quiet = canvas.exported();
    canvas.editor.select(["west"]);
    canvas.editor.startWire("east.B");
    canvas.requestUpdate();
    await canvas.updateComplete;
    expect(canvas.renderRoot.querySelector(".symbol.selected")).not.toBeNull();
    expect(canvas.renderRoot.querySelector(".faces")).not.toBeNull();
    expect(canvas.exported()).toBe(quiet);
    canvas.remove();
  });

  /** The colours and widths live in the canvas's own stylesheet, so a file
   *  without them renders as unstyled black. */
  it("carries the colours the canvas draws with", async () => {
    const canvas = await drawn();
    const written = canvas.exported();
    expect(written).toContain("--paper: #fbfbfa;");
    expect(written).toContain("fill: var(--paper)");
    canvas.remove();
  });
});

/**
 * The way behind a refusal, lit red on the canvas (ADR-0024, #93).
 *
 * A DOM test for the reason the portal label's is: what the store returns has
 * to reach the artwork keyed by symbol, and a model-seam test would stay green
 * with the mark landing nowhere.
 */
describe("the way a refusal is about", () => {
  /** A turnout whose two roads run back into the block they left, which is the
   *  reversal derivation refuses. */
  const LOOP: Drawing = {
    drawing: "loop",
    symbols: {
      west: { kind: "block", at: [0, 0], length: 1000 },
      points: { kind: "turnout", at: [7, 0] },
      east: { kind: "block", at: [10, 0], length: 1000 },
    },
    wires: [],
  };

  async function drawn(offending: Transit[], chosen: Chosen | null = null) {
    const canvas = document.createElement("tc-canvas");
    canvas.editor = new Editor(structuredClone(LOOP));
    canvas.review = { ...reviewed([]), offending };
    canvas.chosen = chosen;
    document.body.append(canvas);
    await canvas.updateComplete;
    return canvas;
  }

  /** Which symbols are marked as the offending way, and whether the way is
   *  lit at all. */
  async function marked(offending: Transit[]) {
    const canvas = await drawn(offending);
    const symbols = [...canvas.renderRoot.querySelectorAll("g.symbol.offending")]
      .map((group) => group.getAttribute("data-symbol")!)
      .sort();
    const legs = canvas.renderRoot.querySelectorAll(
      "g.symbol.offending .lit",
    ).length;
    canvas.remove();
    return { symbols, legs };
  }

  it("lights the symbols on a way that loops back into its own block", async () => {
    const { symbols, legs } = await marked([
      { ends: ["west.B", "west.B"], way: [["points", "straight"]] },
    ]);
    expect(symbols).toEqual(["points", "west"]);
    expect(legs).toBeGreaterThan(0);
  });

  it("lights both ways where two transits derive one name", async () => {
    const { symbols } = await marked([
      { ends: ["east.A", "west.B"], way: [["points", "straight"]] },
      { ends: ["east.A", "west.B"], way: [["points", "diverging"]] },
    ]);
    expect(symbols).toEqual(["east", "points", "west"]);
  });

  it("lights nothing where the refusal is not about a way", async () => {
    expect(await marked([])).toEqual({ symbols: [], legs: 0 });
  });

  it("leaves a transit chosen in the netlist pane lit as it was", async () => {
    const canvas = await drawn([], { connection: "c", transit: "t" });
    canvas.review = {
      ...canvas.review!,
      explain: {
        layout: "loop",
        connections: {
          c: {
            transits: {
              t: { ends: ["east.A", "west.B"], way: [["points", "straight"]] },
            },
            exclusive: [],
          },
        },
      },
    };
    await canvas.updateComplete;
    expect(canvas.renderRoot.querySelectorAll(".lit").length).toBeGreaterThan(0);
    expect(canvas.renderRoot.querySelectorAll(".symbol.offending")).toHaveLength(
      0,
    );
    canvas.remove();
  });
});

/**
 * The wires a lit way runs over (#142).
 *
 * A DOM test because what is being checked is the picture: which lines carry
 * the lit class, and the order they are emitted in — a lit wire drawn under
 * an unlit one it crosses is half hidden, and no model answer can see that.
 * Which wires are on a way is `inspect.wiresOn`, tested at its own seam.
 */
describe("the wires a lit way runs over", () => {
  /** `west` faces a turnout whose straight road leads to `east` and whose
   *  diverging road leads to `north`, with a buffer stop off west's other
   *  end — two wires on the straight way and two off it. */
  const YARD: Drawing = {
    drawing: "yard",
    symbols: {
      west: { kind: "block", at: [0, 0], length: 1000 },
      points: { kind: "turnout", at: [7, 0] },
      east: { kind: "block", at: [10, 0], length: 1000 },
      north: { kind: "block", at: [10, 3], length: 1000 },
      stop: { kind: "terminal", at: [0, 3] },
    },
    wires: [
      ["west.B", "points.toe"],
      ["points.straight", "east.A"],
      ["points.diverging", "north.A"],
      ["west.A", "stop.P"],
    ],
  };

  const STRAIGHT: Transit = {
    ends: ["east.A", "west.B"],
    way: [["points", "straight"]],
  };

  async function lines(review: Partial<Review>, chosen: Chosen | null = null) {
    const canvas = document.createElement("tc-canvas");
    canvas.editor = new Editor(structuredClone(YARD));
    canvas.review = { ...reviewed([]), ...review };
    canvas.chosen = chosen;
    document.body.append(canvas);
    await canvas.updateComplete;
    const drawn = [...canvas.renderRoot.querySelectorAll("line.wire")].map(
      (line) => [...line.classList].join(" "),
    );
    canvas.remove();
    return drawn;
  }

  /** The review a chosen transit is read out of: the netlist pane names the
   *  connection and the transit, and the way comes from the explanation. */
  const explained: Partial<Review> = {
    explain: {
      layout: "yard",
      connections: {
        c: { transits: { t: STRAIGHT }, exclusive: [] },
      },
    },
  };

  it("lights the wires of a transit chosen in the netlist pane", async () => {
    const drawn = await lines(explained, { connection: "c", transit: "t" });
    expect(drawn.filter((classes) => classes.includes("lit"))).toHaveLength(2);
  });

  it("draws the lit wires last, so a crossing unlit one cannot hide one", async () => {
    const drawn = await lines(explained, { connection: "c", transit: "t" });
    expect(drawn.map((classes) => classes.includes("lit"))).toEqual([
      false,
      false,
      true,
      true,
    ]);
  });

  it("lights nothing while nothing is chosen and nothing is refused", async () => {
    const drawn = await lines(explained);
    expect(drawn.filter((classes) => classes.includes("lit"))).toHaveLength(0);
  });

  /** A refusal is about a route, so it points at the whole route — wires
   *  included — in the red that means derivation stopped (ADR-0024). */
  it("lights the wires of a refused way in the refusal colour", async () => {
    const drawn = await lines({ offending: [STRAIGHT] });
    expect(drawn.filter((classes) => classes.includes("offending"))).toHaveLength(
      2,
    );
  });
});

/**
 * The quiet mark a motorised symbol with no address wears (#96, ADR-0024).
 *
 * A DOM test because the mark is a shape on the canvas rather than an answer
 * in the model — `Editor.unaddressed` has its own test — and because what is
 * worth checking is that it sits on the symbol it is about and that no review
 * is consulted for it: a drawing that derives still carries it.
 */
describe("the mark a symbol with no address wears", () => {
  /** One turnout addressed, one not, a slip with none, and a fixed crossing,
   *  which has no motor to address at all. */
  const YARD: Drawing = {
    drawing: "yard",
    symbols: {
      sw1: { kind: "turnout", at: [0, 0], addr: "31" },
      sw2: { kind: "turnout", at: [3, 0] },
      ss1: { kind: "single_slip", at: [6, 0] },
      x1: { kind: "crossing", at: [9, 0] },
      b1: { kind: "block", at: [0, 3], length: 1000 },
    },
    wires: [],
  };

  async function drawn(drawing: Drawing = YARD) {
    const canvas = document.createElement("tc-canvas");
    canvas.editor = new Editor(structuredClone(drawing));
    canvas.review = reviewed([]);
    document.body.append(canvas);
    await canvas.updateComplete;
    return canvas;
  }

  /** Which symbols wear the mark, by the group each one is drawn in. */
  function worn(canvas: TcCanvas): string[] {
    return [...canvas.renderRoot.querySelectorAll(".unaddressed")]
      .map((mark) => mark.closest("g.symbol")!.getAttribute("data-symbol")!)
      .sort();
  }

  it("marks a turnout and a slip carrying none, and nothing else", async () => {
    const canvas = await drawn();
    expect(worn(canvas)).toEqual(["ss1", "sw2"]);
    canvas.remove();
  });

  it("draws it on the squares the symbol covers", async () => {
    const canvas = await drawn();
    const mark = canvas.renderRoot.querySelector(
      'g[data-symbol="ss1"] .unaddressed',
    )!;
    const box = (name: string) => Number(mark.getAttribute(name));
    // A single slip is two squares wide, and the ring sits inside them.
    expect(box("x")).toBeGreaterThanOrEqual(6);
    expect(box("x") + box("width")).toBeLessThanOrEqual(8);
    expect(box("y")).toBeGreaterThanOrEqual(0);
    expect(box("y") + box("height")).toBeLessThanOrEqual(1);
    canvas.remove();
  });

  it("turns with the symbol, the footprint turning with it", async () => {
    const canvas = await drawn({
      ...YARD,
      symbols: { ss1: { kind: "single_slip", at: [6, 0], rot: 90 } },
    });
    const mark = canvas.renderRoot.querySelector(".unaddressed")!;
    expect(Number(mark.getAttribute("width"))).toBeLessThan(
      Number(mark.getAttribute("height")),
    );
    canvas.remove();
  });

  it("clears on the keystroke, no second review being asked for", async () => {
    const canvas = await drawn();
    const spec = canvas.editor.drawing.symbols.sw2!;
    canvas.editor.edit("sw2", "sw2", { ...spec, addr: "32" });
    canvas.requestUpdate();
    await canvas.updateComplete;
    expect(worn(canvas)).toEqual(["ss1"]);
    canvas.remove();
  });
});
