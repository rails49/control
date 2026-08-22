import { css } from "lit";

import { palette } from "./shared.styles.js";

/**
 * The app (`tc-app`): the page every view is laid out on.
 *
 * Three rows — the band, the bar, and the work. The palette of custom
 * properties is declared here, a page being the host every component inherits
 * it from (#86).
 *
 * Both views sit in the work row, in the same cell, and the one that is not
 * current is hidden rather than taken away. Taking it away would close the
 * live session on every toggle, which is the wrong price for looking at the
 * netlist; and `visibility` leaves the hidden view its real width and height,
 * so a canvas fitted while it is hidden fits to the shape it will be seen at.
 */
export const appStyles = css`
  :host {
    ${palette}

    display: grid;
    grid-template-rows: auto auto 1fr;
    grid-template-areas:
      "band"
      "bar"
      "work";
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

  tc-editor,
  tc-panel {
    grid-area: work;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }

  /* Not the HTML hidden attribute: its display:none would take the view's
     width and height away with it, and the shape is the half worth keeping. */
  .off {
    visibility: hidden;
  }
`;
