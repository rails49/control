import { css } from "lit";

import { palette, symbols, way } from "./shared.styles.js";

/** The drawing surface (`tc-canvas`). */
export const canvasStyles = css`
  :host {
    display: block;
    overflow: hidden;
  }

  svg {
    width: 100%;
    height: 100%;
    touch-action: none;
    user-select: none;
  }

  .sheet {
    fill: var(--paper);
  }

  .faces {
    pointer-events: none;
  }

  /* A face centre. Ruled lines would have marked the cell corners, which are
     the one class of point a wire can never land on. */
  .face {
    fill: var(--face);
  }

  /* A square two symbols both cover, marked over the artwork so the overlap a
     rotate or a flip made is visible where it is. In the quieter weight: an
     overlap is cosmetic and the drawing derives regardless, so marking it in
     the red a pin short of a wire wears would overstate it (ADR-0024). Heavier
     than the red mark to make up for the slate, which reads fainter over paper
     at the same opacity. */
  .stacked {
    fill: var(--unfinished);
    opacity: 0.3;
    pointer-events: none;
  }

  /* A junction wearing a name another connection also wears, or two its own
     symbols disagree about: shown where it is rather than only in the panel.
     It is the only tint left on the canvas, so colour here means something is
     wrong rather than merely that a junction is a junction. */
  .junction {
    pointer-events: none;
  }

  .junction rect {
    fill: var(--wrong);
    opacity: 0.14;
  }

  ${symbols}

  /* The wire following the pointer is an affordance rather than track, so it
     keeps its width as the canvas is zoomed. */
  .wireline {
    stroke: var(--chosen);
    stroke-width: 2;
    stroke-dasharray: 6 4;
    vector-effect: non-scaling-stroke;
    pointer-events: none;
  }

  .symbol.selected .track,
  .symbol.selected .wire {
    stroke: var(--chosen);
  }

  .symbol.selected .block-body,
  .symbol.selected .opaque {
    stroke: var(--chosen);
  }

  /* The wire, the lit way and the box, after the selection rules: a symbol
     both selected and on the way shows the way — which is the answer to the
     question selecting it asked. */
  ${way}

  /* The way a refusal is about, lit in the red that means derivation stopped
     rather than in the colour a chosen transit wears (ADR-0024). It reads as
     one run for the same reason a chosen transit does — every leg of it and
     both its block ends — and the rules ride on the lit classes so that what
     is lit stays one answer with one shape. */
  .symbol.offending .track.lit {
    stroke: var(--wrong);
  }

  .symbol.offending .tick.lit {
    stroke: var(--wrong);
  }

  .symbol.offending .bend.lit {
    fill: var(--wrong);
  }

  .symbol.offending .block-body.lit,
  .symbol.offending .opaque.lit {
    fill: var(--wrong-body);
    stroke: var(--wrong);
  }

  /* A block's label, the only text on a symbol: centred in its rectangle rather
     than sitting on a point. The size is set per label rather than here, being
     the size that name fits the rectangle at (render/units.ts). */
  .name {
    font-family: system-ui, sans-serif;
    fill: var(--ink);
    text-anchor: middle;
    dominant-baseline: middle;
    pointer-events: none;
  }

  /* The label a portal pairing with nothing wears, beside its mouth: the only
     text a symbol other than a block carries, and there only while the drawing
     is wrong, so colour on the canvas still means trouble
     (EDITOR.md#symbol-geometry).

     It is not a name rule, though it is drawn like one: a name is what a symbol
     carries and this is a finding, and which end of it sits on the point is
     the mark's own direction speaking, through the attribute a rule here would
     beat. */
  .unpaired {
    font-family: system-ui, sans-serif;
    fill: var(--wrong);
    dominant-baseline: middle;
    pointer-events: none;
  }

  /* Every pin is drawn while editing, green where it has the wire it wants and
     red where it does not. The verdict is the store's, not the canvas's. */
  .pin {
    fill: var(--good);
  }

  .pin.red {
    fill: var(--wrong);
  }

  .pin.pending {
    fill: var(--chosen);
  }

  /* The symbol on its way out of the palette, drawn where a drop would put it.
     Faint, so what is already on the sheet reads through it and the ghost is
     plainly not placed yet; the squares it cannot have are marked where they
     are, as an overlap is. */
  .ghost {
    opacity: 0.45;
    pointer-events: none;
  }

  .ghost.blocked {
    opacity: 0.3;
  }

  /* Under the ghost the same square is a refusal rather than an overlap: the
     drop places nothing (EDITOR.md#canvas), and what stops something is red.
     The rule sits on the ancestor rather than on a class of its own, so the
     mark cannot be renamed on one side and left on the other. */
  .ghost.blocked .stacked {
    fill: var(--wrong);
    opacity: 0.22;
  }

  .band {
    fill: var(--chosen);
    fill-opacity: 0.08;
    stroke: var(--chosen);
    stroke-width: 1;
    stroke-dasharray: 4 3;
    vector-effect: non-scaling-stroke;
  }
`;

/**
 * What an exported file carries: the canvas's rules, and the palette they
 * read (#86).
 *
 * On screen the custom properties come off `tc-editor`'s host and the canvas
 * inherits them; a file has no host above it, so they are written onto the svg
 * itself. Both sides read the same `COLOURS`, and the rules are `canvasStyles`
 * itself rather than a copy of it, so the file cannot drift from the screen.
 */
export const exportStyles = css`
  svg {
    ${palette}
  }

  ${canvasStyles}
`;
