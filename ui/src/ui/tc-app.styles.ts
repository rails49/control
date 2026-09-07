import { css, unsafeCSS } from "lit";

import { RAIL_TURNS_PX } from "../render/units.js";
import { palette } from "./shared.styles.js";

/**
 * The app (tc-app): the page every view is laid out on.
 *
 * A band across the top and a rail down the left of the work
 * ([ADR-0064](../../../docs/adr/0064-the-chrome-is-a-band-and-a-rail.md)), and
 * the work itself. The palette of custom properties is declared here, a page
 * being the host every component inherits it from (#86).
 *
 * Each view fills the work with a left pane and its surface, and the shell is
 * where that pane's width is declared: one left-pane slot with a view's pane in
 * it — the editor's palette, the run view's roster
 * ([#169](https://github.com/rails49/control/issues/169)). Two views agreeing
 * on a number would be two places to change it, and the panes would drift
 * apart across a toggle.
 *
 * Every view sits in the work, in the same cell, and the ones that are not
 * current are hidden rather than taken away. Taking it away would close the
 * live session on every toggle, which is the wrong price for looking at the
 * netlist; and visibility leaves the hidden view its real width and height,
 * so a canvas fitted while it is hidden fits to the shape it will be seen at.
 */
export const appStyles = css`
  :host {
    ${palette}

    /* The left-pane slot every view fills: the palette in edit, the roster in
       run. */
    --pane: 12rem;

    /* The rail's own width, which is the column the work starts after. Stated
       here as well as read there, the grid being what has to leave room for
       it. */
    --rail-width: 3rem;

    display: grid;
    grid-template-columns: auto 1fr;
    grid-template-rows: auto 1fr;
    grid-template-areas:
      "band band"
      "rail work";
    height: 100vh;
    background: var(--paper);
    color: var(--ink);
    font: 13px/1.4 system-ui, sans-serif;
  }

  /* The band's picker hangs over the rail and the work. z-index only competes
     inside one stacking context, and a shadow root establishes none, so the
     context is made here rather than left to the painting order — which is DOM
     order, and would put the rail over the list hanging off the band. */
  tc-header {
    position: relative;
    z-index: 20;
    grid-area: band;
  }

  tc-rail {
    position: relative;
    z-index: 10;
    grid-area: rail;
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

  /* A window too short for the rail's column. It lies down along the top of
     the work and the grid gives it a row of its own to lie in; tc-rail turns
     its own contents at the same height, which is why the number is
     RAIL_TURNS_PX in both (render/units.ts). */
  @media (max-height: ${unsafeCSS(RAIL_TURNS_PX)}px) {
    :host {
      grid-template-columns: 1fr;
      grid-template-rows: auto auto 1fr;
      grid-template-areas:
        "band"
        "rail"
        "work";
    }
  }
`;
