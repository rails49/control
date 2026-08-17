/**
 * The editor's styles, kept out of the components so that what a component
 * has is behaviour. Colours are custom properties on `tc-editor`, which is
 * where a theme would be set.
 */

import { css } from "lit";

export const appStyles = css`
  :host {
    --ink: #1c1f24;
    --paper: #fbfbfa;
    --rule: #d9d6d0;
    --track: #2b3038;
    --chosen: #1f6feb;
    --wrong: #cc2936;
    --hint: #7c8087;
    --tint-0: #1f6feb;
    --tint-1: #14866d;
    --tint-2: #a55b12;
    --tint-3: #8250df;
    --tint-4: #b3417a;
    --tint-5: #56761c;

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

export const paletteStyles = css`
  :host {
    display: block;
    padding: 0.4rem;
  }

  h2 {
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint, #7c8087);
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
    border-color: var(--chosen, #1f6feb);
    background: #e8f0fe;
  }

  svg {
    width: 3rem;
    height: 1.6rem;
    flex: none;
  }

  .track {
    fill: none;
    stroke: var(--track, #2b3038);
    stroke-width: 0.09;
    stroke-linecap: round;
  }

  .block-body {
    fill: #dfe3e8;
    stroke: var(--track, #2b3038);
    stroke-width: 0.05;
  }

  .signal {
    fill: var(--track, #2b3038);
  }

  .mast,
  .stop {
    fill: none;
    stroke: var(--track, #2b3038);
    stroke-width: 0.06;
  }

  .sensor {
    fill: var(--hint, #7c8087);
  }

  .portal-mouth {
    fill: none;
    stroke: var(--track, #2b3038);
    stroke-width: 0.06;
  }

  .bend {
    fill: var(--track, #2b3038);
  }
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
    fill: var(--paper, #fbfbfa);
  }

  .squares {
    pointer-events: none;
  }

  .grid {
    fill: none;
    stroke: var(--rule, #d9d6d0);
    stroke-width: 0.02;
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
    fill: var(--wrong, #cc2936);
    opacity: 0.14;
  }

  .junction.clashing text {
    fill: var(--wrong, #cc2936);
  }

  .tint-0 {
    color: var(--tint-0, #1f6feb);
  }
  .tint-1 {
    color: var(--tint-1, #14866d);
  }
  .tint-2 {
    color: var(--tint-2, #a55b12);
  }
  .tint-3 {
    color: var(--tint-3, #8250df);
  }
  .tint-4 {
    color: var(--tint-4, #b3417a);
  }
  .tint-5 {
    color: var(--tint-5, #56761c);
  }

  .wire {
    stroke: var(--track, #2b3038);
    stroke-width: 2.5;
    stroke-linecap: round;
    vector-effect: non-scaling-stroke;
  }

  .wireline {
    stroke: var(--chosen, #1f6feb);
    stroke-width: 2;
    stroke-dasharray: 6 4;
    vector-effect: non-scaling-stroke;
    pointer-events: none;
  }

  .track {
    fill: none;
    stroke: var(--track, #2b3038);
    stroke-width: 2.5;
    stroke-linecap: round;
    vector-effect: non-scaling-stroke;
  }

  .slip {
    stroke-dasharray: 5 3;
  }

  .block-body {
    fill: #dfe3e8;
    stroke: var(--track, #2b3038);
    stroke-width: 1.2;
    vector-effect: non-scaling-stroke;
  }

  .signal {
    fill: var(--track, #2b3038);
  }

  .mast,
  .stop,
  .portal-mouth {
    fill: none;
    stroke: var(--track, #2b3038);
    stroke-width: 1.6;
    vector-effect: non-scaling-stroke;
  }

  .sensor {
    fill: var(--hint, #7c8087);
  }

  .bend {
    fill: var(--track, #2b3038);
  }

  /* The generic connection symbol shows no turnout detail, which is what it
     says about itself. */
  .opaque {
    fill: #edeae4;
    stroke: var(--track, #2b3038);
    stroke-width: 1.4;
    stroke-dasharray: 5 3;
    vector-effect: non-scaling-stroke;
  }

  .symbol.selected .track,
  .symbol.selected .wire {
    stroke: var(--chosen, #1f6feb);
  }

  .symbol.selected .block-body,
  .symbol.selected .opaque {
    stroke: var(--chosen, #1f6feb);
  }

  /* The way a chosen transit takes, leg by leg: the legs of the symbols on it,
     and the two block ends it runs between. After the selection rules, so that
     a symbol both selected and on the way shows the way — which is the answer
     to the question selecting it asked. */
  .symbol .track.lit {
    stroke: var(--tint-2, #a55b12);
    stroke-width: 4.5;
  }

  .symbol .bend.lit {
    fill: var(--tint-2, #a55b12);
  }

  /* A block's body covers all but the stubs of its track, so the end of a lit
     transit would otherwise be two orange flecks. */
  .symbol .block-body.lit,
  .symbol .opaque.lit {
    fill: #f4e3cd;
    stroke: var(--tint-2, #a55b12);
  }

  .name {
    font: 0.22px system-ui, sans-serif;
    fill: var(--hint, #7c8087);
    text-anchor: middle;
    pointer-events: none;
  }

  .pin {
    fill: var(--paper, #fbfbfa);
    stroke: var(--track, #2b3038);
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
  }

  .pin.red {
    fill: var(--wrong, #cc2936);
    stroke: var(--wrong, #cc2936);
  }

  .pin.pending {
    fill: var(--chosen, #1f6feb);
    stroke: var(--chosen, #1f6feb);
  }

  .band {
    fill: var(--chosen, #1f6feb);
    fill-opacity: 0.08;
    stroke: var(--chosen, #1f6feb);
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
    border: 1px solid var(--rule, #d9d6d0);
    border-radius: 5px;
    background: var(--paper, #fbfbfa);
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
    color: var(--ink, #1c1f24);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  button:hover {
    background: var(--chosen, #1f6feb);
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
    color: var(--hint, #7c8087);
  }

  .hint {
    margin: 0 0 0.5rem;
    color: var(--hint, #7c8087);
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
    color: var(--hint, #7c8087);
  }

  h2 {
    color: var(--ink, #1c1f24);
  }

  .count {
    font-weight: 400;
    color: var(--hint, #7c8087);
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
    border-left: 3px solid var(--tint-2, #a55b12);
    background: #faf5ee;
  }

  .concurrent {
    margin: 0.15rem 0 0.3rem 0.3rem;
    color: var(--tint-1, #14866d);
  }

  .concurrent li::before {
    content: "runs with  ";
    color: var(--hint, #7c8087);
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
    color: var(--hint, #7c8087);
    font-variant-numeric: tabular-nums;
  }

  .against {
    margin: 0.2rem 0 0.5rem 0.8rem;
    border-left: 2px solid var(--rule, #d9d6d0);
  }

  .against li {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.1rem 0.4rem;
  }

  .against .with span:first-child {
    color: var(--tint-1, #14866d);
  }

  .against .without span:first-child {
    color: var(--wrong, #cc2936);
  }

  .hint {
    color: var(--hint, #7c8087);
  }
`;
