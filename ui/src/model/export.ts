/**
 * The drawing as a standalone SVG file (#86).
 *
 * The picture is the canvas's own markup, cloned rather than re-rendered from
 * the document: composing the sheet, the wires, the pins and the marks a
 * second time would be a second implementation of `tc-canvas`, free to
 * drift from what is on screen — the failure mode EDITOR.md#implementation
 * rules out for the netlist and rules out here for the same reason.
 *
 * Only the clone needs a document, so only that is the component's. What the
 * file says around it is here: the frame it is drawn in, the size it opens at,
 * and which of the canvas's parts are a gesture in progress rather than the
 * drawing. That is neither the document nor the DOM, so it is a module in
 * `model/` with a test (EDITOR.md#tests).
 *
 * The stylesheet comes in as text because it is `ui/`'s and `model/` imports
 * no `ui/`. What the component hands over is `canvasStyles` itself, so the file
 * cannot drift from the screen: it is the object the canvas renders with.
 */

import type { Box } from "./scene.js";

/** The parts of the canvas that are a gesture in progress: the landing marks
 *  drawn while a wire is in flight, the wire itself, the rubber band, and the
 *  symbol on its way out of the palette. None of them is the drawing, so
 *  exporting mid-gesture gives the file it would have given without one. */
export const TRANSIENT: string[] = [".faces", ".wireline", ".band", ".ghost"];

/** The classes a part of the drawing wears only while a gesture is in
 *  progress: the selection highlight, and the pin a wire is coming from. The
 *  node stays and the class goes. */
export const GESTURING: string[] = ["selected", "pending"];

/** How large a grid square opens at, in pixels. The file has no pane to fill,
 *  so it carries a size; this is the one the plates in EDITOR.md are drawn
 *  at. */
const SQUARE = 44;

export interface Sheet {
  /** The frame, in grid squares. */
  box: Box;
  /** The canvas's stylesheet, whole. */
  styles: string;
  /** The canvas's markup, cloned and cleaned. */
  body: string;
}

/** One standalone SVG document: the frame, the stylesheet, and the markup. */
export function svgFile({ box, styles, body }: Sheet): string {
  const width = Math.round(box.w * SQUARE);
  const height = Math.round(box.h * SQUARE);
  return `${[
    `<svg xmlns="http://www.w3.org/2000/svg"` +
      ` viewBox="${box.x} ${box.y} ${box.w} ${box.h}"` +
      ` width="${width}" height="${height}">`,
    "<style>",
    styles,
    // The canvas sizes its svg to the pane it sits in, and that rule is in the
    // stylesheet the file carries. A file has no pane, so the size the
    // attributes give is pinned back over it.
    `svg { width: ${width}px; height: ${height}px; }`,
    "</style>",
    body,
    "</svg>",
  ].join("\n")}\n`;
}
