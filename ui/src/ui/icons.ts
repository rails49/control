/**
 * The header's icons, drawn here rather than fetched.
 *
 * Shoelace's `sl-icon` loads its SVGs from a CDN at runtime unless a base path
 * is registered, and the editor has to work on the railroad's own network
 * (EDITOR.md#implementation). Five glyphs are cheaper than vendoring an icon
 * set for them.
 *
 * Each is drawn on a 16 unit square and inherits `currentColor`, so a button's
 * own colour and disabled state carry through without a second rule.
 */

import { svg, type SVGTemplateResult } from "lit";

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
