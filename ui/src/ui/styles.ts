/**
 * The editor's styles, kept out of the components so that what a component
 * has is behaviour.
 *
 * Every dimension and every colour comes from `render/units.ts`: the colours
 * are declared here as the custom properties on `tc-editor` that the rules
 * below read, and the widths are interpolated straight in, so a stroke is W
 * wide because W says so and not because two files agree.
 */

import { css, unsafeCSS } from "lit";

import {
  BLOCK,
  COLOURS,
  HAIRLINE,
  LABEL,
  SLIP,
  TERMINAL,
  W,
} from "../render/units.js";

/** The palette, as the custom properties every rule reads. */
const palette = unsafeCSS(
  Object.entries(COLOURS)
    .map(([name, value]) => `${name}: ${value};`)
    .join("\n    "),
);

export const appStyles = css`
  :host {
    ${palette}

    display: grid;
    grid-template-rows: auto 1fr;
    grid-template-columns: 12rem 1fr 22rem;
    grid-template-areas:
      "bar bar bar"
      "palette canvas side";
    height: 100vh;
    background: var(--paper);
    color: var(--ink);
    font: 13px/1.4 system-ui, sans-serif;
  }

  header {
    grid-area: bar;
    display: flex;
    gap: 0.5rem;
    align-items: center;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--rule);
  }

  header .spacer {
    flex: 1;
  }

  header .drawing {
    font-weight: 600;
  }

  tc-palette {
    grid-area: palette;
    border-right: 1px solid var(--rule);
    overflow-y: auto;
  }

  tc-canvas {
    grid-area: canvas;
    min-width: 0;
  }

  .side {
    grid-area: side;
    border-left: 1px solid var(--rule);
    overflow-y: auto;
    padding: 0.6rem;
  }

  .findings {
    margin: 0 0 0.8rem;
    padding: 0.5rem 0.6rem;
    border-left: 3px solid var(--wrong);
    background: #fdf0f0;
  }

  .findings.clean {
    border-left-color: var(--tint-1);
    background: #eef7f3;
  }

  .findings p {
    margin: 0.15rem 0;
  }

  .hint {
    color: var(--hint);
  }
`;

/**
 * The symbols themselves, drawn the same on the canvas and on a palette tile:
 * both are the symbol's own coordinates, one grid square to one user unit, so
 * one set of rules serves both and a tile shows what will be placed. Track is
 * solid and round-capped, never patterned — wires run at any angle, and a
 * pattern's spacing would vary with direction.
 */
const symbols = css`
  .track {
    fill: none;
    stroke: var(--track);
    stroke-width: ${W};
    stroke-linecap: round;
  }

  /* White in edit mode; run mode, out of scope for now, recolours it by
     occupancy through the same class. */
  .block-body {
    fill: var(--body);
    stroke: var(--track);
    stroke-width: ${BLOCK.body.border};
  }

  /* A stroke ending inside another shape is cut square, so that a round cap
     cannot bulge past a buffer bar. */
  .track.cut {
    stroke-linecap: butt;
  }

  .plaque {
    fill: var(--track);
  }

  /* Both aspects are drawn, and edit mode shows both lit. Run mode, out of
     scope for now, dims the one the signal is not showing. */
  .lamp.clear {
    fill: var(--clear);
  }

  .lamp.danger {
    fill: var(--danger);
  }

  .stop,
  .mark,
  .portal-mouth,
  .tick {
    fill: none;
    stroke: var(--track);
    stroke-linecap: butt;
  }

  /* The plus marking a block's A side, at the weight of the rectangle it sits
     on the corner of. */
  .mark {
    stroke-width: ${BLOCK.body.border};
  }

  .stop {
    stroke-width: ${TERMINAL.bar.w};
  }

  .portal-mouth {
    stroke: var(--hint);
    stroke-width: ${HAIRLINE};
  }

  .tick {
    stroke-width: ${SLIP.weight};
  }
`;

export const paletteStyles = css`
  :host {
    display: block;
    padding: 0.4rem;
  }

  h2 {
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
    margin: 0.3rem 0.2rem;
  }

  button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.3rem;
    margin-bottom: 0.2rem;
    border: 1px solid transparent;
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  button:hover {
    background: #f0eeea;
  }

  button[aria-pressed="true"] {
    border-color: var(--chosen);
    background: #e8f0fe;
  }

  /* A tile keeps its symbol's own shape: the height is fixed and the width
     follows the footprint, so a block reads as the long thing it is instead of
     being letterboxed into a square. */
  svg {
    height: 1.5rem;
    width: auto;
    max-width: 5rem;
    flex: none;
  }

  /* Definitions only, shared by every tile: sized to nothing so it takes no
     room, rather than hidden, which would take its contents out of reach. */
  svg.defs {
    position: absolute;
    width: 0;
    height: 0;
  }

  ${symbols}
`;

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

  .squares {
    pointer-events: none;
  }

  .grid {
    fill: none;
    stroke: var(--rule);
    stroke-width: 0.02;
  }

  /* A square two symbols both cover, marked over the artwork so the overlap a
     rotate or a flip made is visible where it is. */
  .stacked {
    fill: var(--wrong);
    opacity: 0.22;
    pointer-events: none;
  }

  .junction {
    pointer-events: none;
  }

  .junction rect {
    fill: currentColor;
    opacity: 0.1;
  }

  .junction text {
    font: 0.26px system-ui, sans-serif;
    font-weight: 600;
    fill: currentColor;
  }

  /* A junction wearing a name another connection also wears, or two its own
     symbols disagree about: shown where it is rather than only in the panel. */
  .junction.clashing rect {
    fill: var(--wrong);
    opacity: 0.14;
  }

  .junction.clashing text {
    fill: var(--wrong);
  }

  .tint-0 {
    color: var(--tint-0);
  }
  .tint-1 {
    color: var(--tint-1);
  }
  .tint-2 {
    color: var(--tint-2);
  }
  .tint-3 {
    color: var(--tint-3);
  }
  .tint-4 {
    color: var(--tint-4);
  }
  .tint-5 {
    color: var(--tint-5);
  }

  ${symbols}

  /* A wire is track: same width, same round cap, so it joins a symbol's leg
     seamlessly at whatever angle its two pins give it. */
  .wire {
    stroke: var(--track);
    stroke-width: ${W};
    stroke-linecap: round;
  }

  /* The wire following the pointer is an affordance rather than track, so it
     keeps its width as the canvas is zoomed. */
  .wireline {
    stroke: var(--chosen);
    stroke-width: 2;
    stroke-dasharray: 6 4;
    vector-effect: non-scaling-stroke;
    pointer-events: none;
  }

  /* The generic connection symbol shows no turnout detail, which is what it
     says about itself. */
  .opaque {
    fill: #edeae4;
    stroke: var(--track);
    stroke-width: ${0.5 * W};
    stroke-dasharray: ${2 * W} ${W};
  }

  .symbol.selected .track,
  .symbol.selected .wire {
    stroke: var(--chosen);
  }

  .symbol.selected .block-body,
  .symbol.selected .opaque {
    stroke: var(--chosen);
  }

  /* The way a chosen transit takes, leg by leg: the legs of the symbols on it,
     and the two block ends it runs between. After the selection rules, so that
     a symbol both selected and on the way shows the way — which is the answer
     to the question selecting it asked. */
  .symbol .track.lit {
    stroke: var(--lit);
    stroke-width: ${1.6 * W};
  }

  .symbol .bend.lit {
    fill: var(--lit);
  }

  /* A slip's tick is the only thing telling its road from the through route, so
     it lights with the transit. It stays a mark: half again its own weight is
     enough to read beside track three times as thick. */
  .symbol .tick.lit {
    stroke: var(--lit);
    stroke-width: ${SLIP.lit};
  }

  /* A block's body covers all but the stubs of its track, so the end of a lit
     transit would otherwise be two orange flecks. */
  .symbol .block-body.lit,
  .symbol .opaque.lit {
    fill: var(--lit-body);
    stroke: var(--lit);
  }

  /* A block's label, the only text on a symbol: centred in its rectangle rather
     than sitting on a point. */
  .name {
    font: ${LABEL.size}px system-ui, sans-serif;
    fill: var(--ink);
    text-anchor: middle;
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

  .band {
    fill: var(--chosen);
    fill-opacity: 0.08;
    stroke: var(--chosen);
    stroke-width: 1;
    stroke-dasharray: 4 3;
    vector-effect: non-scaling-stroke;
  }
`;

export const menuStyles = css`
  .sheet {
    position: fixed;
    inset: 0;
    z-index: 10;
  }

  menu {
    position: fixed;
    z-index: 11;
    margin: 0;
    padding: 0.25rem;
    list-style: none;
    min-width: 12rem;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--paper);
    box-shadow: 0 6px 18px rgb(0 0 0 / 0.14);
    font: 13px/1.4 system-ui, sans-serif;
  }

  button {
    display: block;
    width: 100%;
    padding: 0.3rem 0.5rem;
    border: none;
    border-radius: 3px;
    background: none;
    color: var(--ink);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  button:hover {
    background: var(--chosen);
    color: #fff;
  }
`;

export const propertiesStyles = css`
  sl-input,
  sl-select {
    display: block;
    margin-bottom: 0.7rem;
  }

  h3 {
    margin: 1rem 0 0.4rem;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
  }

  .hint {
    margin: 0 0 0.5rem;
    color: var(--hint);
  }
`;

export const netlistStyles = css`
  :host {
    display: block;
    font: 13px/1.45 system-ui, sans-serif;
  }

  h2,
  h3 {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    margin: 0.9rem 0 0.3rem;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
  }

  h2 {
    color: var(--ink);
  }

  .count {
    font-weight: 400;
    color: var(--hint);
    text-transform: none;
    letter-spacing: 0;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* The symbol inspector sits above the netlist: it answers the question just
     asked on the canvas, and scrolling to find it would be the wrong way
     round. */
  section.symbol {
    margin-bottom: 0.9rem;
    padding: 0.1rem 0.5rem 0.5rem;
    border-left: 3px solid var(--tint-2);
    background: #faf5ee;
  }

  .concurrent {
    margin: 0.15rem 0 0.3rem 0.3rem;
    color: var(--tint-1);
  }

  .concurrent li::before {
    content: "runs with  ";
    color: var(--hint);
  }

  .blocks li {
    display: flex;
    justify-content: space-between;
    padding: 0.1rem 0.3rem;
  }

  .transits button {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    width: 100%;
    padding: 0.2rem 0.3rem;
    border: none;
    border-radius: 3px;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .transits button:hover {
    background: #f0eeea;
  }

  .transits button.on {
    background: #e8f0fe;
    font-weight: 600;
  }

  .ends,
  .why {
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  .against {
    margin: 0.2rem 0 0.5rem 0.8rem;
    border-left: 2px solid var(--rule);
  }

  .against li {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.1rem 0.4rem;
  }

  .against .with span:first-child {
    color: var(--tint-1);
  }

  .against .without span:first-child {
    color: var(--wrong);
  }

  .hint {
    color: var(--hint);
  }
`;
