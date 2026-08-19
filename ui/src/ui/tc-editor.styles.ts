import { css } from "lit";

import { palette } from "./shared.styles.js";

/** The shell (`tc-editor`): the page it lays its panes out on.
 *
 * Two columns by default, the palette and the drawing. The netlist is a
 * debugging view opened from `View ▸ Netlist` (ADR-0024), and while it is shut
 * the shell renders no `tc-netlist` at all — so the third column is not
 * declared either, and the canvas has the width rather than a 22rem gap. The
 * shell reflects `netlist` onto its host, which is what a stylesheet can
 * read. */
export const appStyles = css`
  :host {
    ${palette}

    display: grid;
    grid-template-rows: auto auto 1fr;
    grid-template-columns: 12rem 1fr;
    grid-template-areas:
      "band band"
      "bar bar"
      "palette canvas";
    height: 100vh;
    background: var(--paper);
    color: var(--ink);
    font: 13px/1.4 system-ui, sans-serif;
  }

  :host([netlist]) {
    grid-template-columns: 12rem 1fr 22rem;
    grid-template-areas:
      "band band band"
      "bar bar bar"
      "palette canvas side";
  }

  tc-header {
    grid-area: band;
  }

  tc-menubar {
    grid-area: bar;
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

  tc-netlist {
    grid-area: side;
    border-left: 1px solid var(--rule);
    overflow-y: auto;
    padding: 0.6rem;
  }

  .hint {
    color: var(--hint);
  }
`;
