/**
 * The file `File ▸ Export SVG…` writes, assembled with no DOM.
 *
 * The clone of the canvas is the component's, being the one part that needs a
 * document; what the file says around it — the frame it is drawn in, the size
 * it opens at, and which of the canvas's parts are a gesture rather than the
 * drawing — is neither the document nor the DOM, so it is a module in `model/`
 * with a test (EDITOR.md#tests).
 */

import { describe, expect, it } from "vitest";

import { GESTURING, SQUARE, TRANSIENT, svgFile } from "../src/model/export.js";

const BOX = { x: -1, y: -1, w: 10, h: 6 };

function file(body = "<rect class='sheet' />"): string {
  return svgFile({ box: BOX, styles: ".track { stroke: #12151a; }", body });
}

describe("the document", () => {
  it("is a standalone SVG framed on the box it is given", () => {
    const written = file();
    expect(written.startsWith("<svg xmlns=")).toBe(true);
    expect(written).toContain('viewBox="-1 -1 10 6"');
    expect(written.trimEnd().endsWith("</svg>")).toBe(true);
  });

  it("carries the drawing's markup as it stands", () => {
    expect(file("<line class='wire' />")).toContain("<line class='wire' />");
  });

  /** The canvas keeps its colours and widths in a stylesheet inside its shadow
   *  root, so `outerHTML` alone renders as unstyled black. The rules come in
   *  whole rather than as a second copy of them kept here. */
  it("inlines the stylesheet it is handed", () => {
    expect(file()).toContain("<style>\n.track { stroke: #12151a; }");
  });

  /** The canvas fills the pane it sits in; a file has no pane, so it opens at
   *  a size of its own — the box in grid squares, at SQUARE pixels each. */
  it("opens at the box's own size, over the rule that fills a pane", () => {
    const written = file();
    expect(written).toContain(`width="${10 * SQUARE}" height="${6 * SQUARE}"`);
    const pinned = `svg { width: ${10 * SQUARE}px; height: ${6 * SQUARE}px; }`;
    expect(written).toContain(pinned);
    expect(written.indexOf(pinned)).toBeGreaterThan(written.indexOf(".track"));
  });

  /** Nothing in it is read off a clock or a counter, so the same drawing
   *  exported twice is the same file. */
  it("says the same thing twice", () => {
    expect(file()).toBe(file());
  });
});

/** A gesture in progress is not the drawing: exporting mid-wire, or with a
 *  symbol selected, gives the file it would have given without either. */
describe("what is a gesture and not the drawing", () => {
  it("names the parts drawn only while one is in flight", () => {
    expect(TRANSIENT).toEqual([".faces", ".wireline", ".band", ".ghost"]);
  });

  it("names the classes a part wears only while one is in flight", () => {
    expect(GESTURING).toEqual(["selected", "pending"]);
  });
});
