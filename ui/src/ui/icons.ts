/**
 * The menu bar's icons, drawn here rather than fetched.
 *
 * Shoelace's `sl-icon` loads its SVGs from a CDN at runtime unless a base path
 * is registered, and the editor has to work on the railroad's own network
 * (EDITOR.md#implementation). Fourteen glyphs are cheaper than vendoring an
 * icon set for them.
 *
 * Each is drawn on a 16 unit square and inherits `currentColor`, so a button's
 * own colour and disabled state carry through without a second rule.
 *
 * `GLYPHS` is keyed by `CommandId` and exhaustive, which is what keeps this
 * file and `model/commands.ts` from drifting apart: a command declared without
 * a glyph is a compile error. The glyphs live here rather than beside the
 * declarations because they are `lit` templates and `model/` imports no
 * `ui/`.
 */

import { svg, type SVGTemplateResult } from "lit";

import type { CommandId } from "../model/commands.js";

/** One glyph, with the stroke settings every one of them shares. */
function icon(body: SVGTemplateResult): SVGTemplateResult {
  return svg`
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      ${body}
    </svg>
  `;
}

/** An arrow curving back on itself, and its mirror. */
export const UNDO = icon(svg`
  <path d="M6 5.5H9.5A3.5 3.5 0 0 1 9.5 12.5H5" />
  <path d="M8 3 5.5 5.5 8 8" />
`);

export const REDO = icon(svg`
  <path d="M10 5.5H6.5A3.5 3.5 0 0 0 6.5 12.5H11" />
  <path d="M8 3l2.5 2.5L8 8" />
`);

/** Four corners pushed outward: the whole drawing brought into view. */
export const FIT = icon(svg`
  <path d="M2.5 6V2.5H6" />
  <path d="M10 2.5h3.5V6" />
  <path d="M13.5 10v3.5H10" />
  <path d="M6 13.5H2.5V10" />
`);

const GLASS = svg`
  <circle cx="7" cy="7" r="4.5" />
  <path d="M10.4 10.4 14 14" />
`;

export const ZOOM_IN = icon(svg`
  ${GLASS}
  <path d="M7 5v4M5 7h4" />
`);

export const ZOOM_OUT = icon(svg`
  ${GLASS}
  <path d="M5 7h4" />
`);

/** A page with its corner turned: the empty drawing New… opens. */
export const NEW = icon(svg`
  <path d="M9 2.5H4.5A1 1 0 0 0 3.5 3.5v9a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V6z" />
  <path d="M9 2.5V6h3.5" />
`);

/** A folder: the drawings there are to open. */
export const OPEN = icon(svg`
  <path d="M2 12.5v-9h4l1.5 2H14v7a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z" />
`);

/** A floppy disk, still what saving looks like. The shutter is at the top and
 *  the label at the bottom, the way one is held. */
export const SAVE = icon(svg`
  <path d="M2.5 3.5a1 1 0 0 1 1-1h7l3 3v7a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1z" />
  <path d="M5 2.5v3.5h4.5V2.5" />
  <path d="M4.5 13.5V9.5h7v4" />
`);

/** The same disk, smaller, with a pen beside its corner: the copy is written
 *  under a name that is typed. */
export const SAVE_AS = icon(svg`
  <path d="M1.8 3.3a.8.8 0 0 1 .8-.8h5.6l2.6 2.6v5.6a.8.8 0 0 1-.8.8H2.6a.8.8 0 0 1-.8-.8z" />
  <path d="M4 2.5v2.9h3.6V2.5" />
  <path d="M3.7 11.5V8.6h5.1v2.9" />
  <path d="M14.2 9.1 9.9 13.4l-2.1.6.6-2.1z" />
`);

/** A tray with an arrow leaving it: the drawing on its way out as a file. */
export const EXPORT = icon(svg`
  <path d="M8 10V2.5" />
  <path d="M5.5 5 8 2.5 10.5 5" />
  <path d="M3 9.5v3a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-3" />
`);

/** An arrow going the whole way round: a symbol turned a quarter at a time. */
export const ROTATE = icon(svg`
  <path d="M13.2 9.8A5.5 5.5 0 1 1 11.9 4.1L14.8 7.2" />
  <path d="M14.8 3.1V7.2H11.1" />
`);

/** Two triangles either side of the axis they mirror across. */
export const FLIP = icon(svg`
  <path d="M8 2v12" stroke-dasharray="1.6 1.7" />
  <path d="M6 4.5 2.5 8 6 11.5z" />
  <path d="M10 4.5 13.5 8 10 11.5z" />
`);

/** A bin: the symbols in the selection, gone. */
export const DELETE = icon(svg`
  <path d="M3 4.5h10" />
  <path d="M6.5 4.5V3.2a.7.7 0 0 1 .7-.7h1.6a.7.7 0 0 1 .7.7v1.3" />
  <path d="M4.5 4.5l.6 8.1a1 1 0 0 0 1 .9h3.8a1 1 0 0 0 1-.9l.6-8.1" />
`);

/** Sliders: the fields a symbol has to set. */
export const PROPERTIES = icon(svg`
  <path d="M2.5 5.5h10M2.5 10.5h10" />
  <circle cx="6" cy="5.5" r="1.7" />
  <circle cx="10" cy="10.5" r="1.7" />
`);

/** The glyph beside each command's label, and on the three buttons the bar
 *  pins at its right end. Exhaustive over `CommandId` by its type. */
export const GLYPHS: Record<CommandId, SVGTemplateResult> = {
  new: NEW,
  open: OPEN,
  save: SAVE,
  "save-as": SAVE_AS,
  "export-svg": EXPORT,
  undo: UNDO,
  redo: REDO,
  rotate: ROTATE,
  flip: FLIP,
  delete: DELETE,
  properties: PROPERTIES,
  "zoom-in": ZOOM_IN,
  "zoom-out": ZOOM_OUT,
  fit: FIT,
};
