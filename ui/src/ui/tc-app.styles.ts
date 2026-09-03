import { css } from "lit";

import { palette } from "./shared.styles.js";

/**
 * The app (`tc-app`): the page every view is laid out on.
 *
 * Three rows — the band, the bar, and the work. The palette of custom
 * properties is declared here, a page being the host every component inherits
 * it from (#86).
 *
 * Each view fills the work row with a left pane and its surface, and the
 * shell is where that pane's width is declared: one left-pane slot with a
 * view's pane in it — the editor's palette, the run view's roster
 * ([#169](https://github.com/rails49/control/issues/169)). Two views agreeing
 * on a number would be two places to change it, and the panes would drift
 * apart across a toggle.
 *
 * Every view sits in the work row, in the same cell, and the ones that are not
 * current are hidden rather than taken away. Taking it away would close the
 * live session on every toggle, which is the wrong price for looking at the
 * netlist; and `visibility` leaves the hidden view its real width and height,
 * so a canvas fitted while it is hidden fits to the shape it will be seen at.
 */
export const appStyles = css`
  :host {
    ${palette}

    /* The left-pane slot every view fills: the palette in edit, the roster in
       run. */
    --pane: 12rem;

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

  /* The rows stack the way they read: the band's picker hangs over the bar,
     and the bar's menus hang over the work. z-index only competes inside one
     stacking context, and a shadow root establishes none, so the contexts are
     made here rather than left to the painting order — which is DOM order, and
     would put the bar's own text over the list hanging off the band. */
  tc-header {
    position: relative;
    z-index: 20;
    grid-area: band;
  }

  tc-menubar {
    position: relative;
    z-index: 10;
    grid-area: bar;
  }

  tc-editor,
  tc-panel,
  tc-stock,
  tc-throttle {
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
