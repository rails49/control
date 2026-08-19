import { css } from "lit";

import { palette } from "./shared.styles.js";

/** The shell (`tc-editor`): the page it lays its panes out on. */
export const appStyles = css`
  :host {
    ${palette}

    display: grid;
    grid-template-rows: auto auto 1fr;
    grid-template-columns: 12rem 1fr 22rem;
    grid-template-areas:
      "band band band"
      "bar bar bar"
      "palette canvas side";
    height: 100vh;
    background: var(--paper);
    color: var(--ink);
    font: 13px/1.4 system-ui, sans-serif;
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
