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
import type { Review, UnpairedPortal } from "../src/model/store.js";

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
    layout: null,
    explain: null,
    refused: null,
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
