import { css, unsafeCSS } from "lit";

import { DRAWING, LEAST, UPRIGHT } from "../model/pane.js";

/**
 * The run view (`tc-panel`): the chrome round the drawing, laid out inside the
 * app's work row.
 *
 * The drawing itself is `tc-canvas`'s, in run mode, so everything that paints
 * a symbol, a wire, a route or a train is declared there and not here
 * ([#168](https://github.com/rails49/control/issues/168)).
 *
 * The pane, the roster with the request list under it (#829, #895), is left
 * of the drawing and takes the full height of the work row. On a page taller
 * than it is wide it is above the drawing, with the two lists side by side
 * ([#1344](https://github.com/rails49/control/issues/1344),
 * [#1390](https://github.com/rails49/control/issues/1390)).
 *
 * The drawing and the two lists are panels on the paper colour, with square
 * corners, on a ground of the gap colour (`--gap`). The ground shows between
 * the two lists.
 *
 * The divider between the pane and the drawing is a 6px gap. It sets the
 * pane's size. The view hands it over as `--pane-size`, and until a person
 * has dragged the divider the width is the shell's `--pane`, which the
 * editor's palette has. The size is held to the limits a drag is held to
 * (`model/pane.ts`) when the window changes size.
 */
export const panelStyles = css`
  :host {
    display: grid;
    grid-template-columns:
      clamp(${LEAST}px, var(--pane-size, var(--pane)), 100% - ${DRAWING.left}px)
      auto 1fr;
    grid-template-rows: auto 1fr;
    grid-template-areas:
      "roster divider notice"
      "roster divider sheet";
    background: var(--gap);
  }

  aside {
    grid-area: roster;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    min-height: 0;
  }

  /* A gap 6px wide. What takes the press is wider, and wider again under a
     finger, and lies over the edges of the pane and the drawing. */
  .divider {
    --reach: 0.3rem;

    grid-area: divider;
    position: relative;
    z-index: 1;
    width: 6px;
    background: var(--gap);
    cursor: col-resize;
    touch-action: none; /* a drag on a touch screen is a drag, not a scroll */
  }

  @media (pointer: coarse) {
    .divider {
      --reach: 0.7rem;
    }
  }

  .divider::before {
    content: "";
    position: absolute;
    inset: 0 calc(-1 * var(--reach));
  }

  .divider:hover,
  .divider:active {
    background: var(--chosen);
  }

  /* The trains are their content's height, capped at half the pane, and the
     requests sit directly under them and take the rest (#895). */
  tc-roster {
    flex: 0 1 auto;
    max-height: 50%;
    overflow-y: auto;
    background: var(--paper);
  }

  tc-requests {
    flex: 1 1 0;
    min-height: 0;
    overflow-y: auto;
    background: var(--paper);
  }

  /* Only drawn while there is something to say, so the row collapses and the
     sheet starts at the top of the view. One line per note: the release
     notice, then a line per train a rebuild took off. */
  header {
    grid-area: notice;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--rule);
    background: var(--paper);
  }

  /* A grid so the canvas fills the row: it is a block element and takes the
     cell's height, which is what a viewport it can be fitted to needs. */
  main {
    grid-area: sheet;
    display: grid;
    overflow: hidden;
    min-height: 0;
    background: var(--paper);
  }

  @media ${unsafeCSS(UPRIGHT)} {
    :host {
      grid-template-columns: 1fr;
      grid-template-rows:
        clamp(${LEAST}px, var(--pane-size, 14rem), 100% - ${DRAWING.above}px)
        auto auto 1fr;
      grid-template-areas:
        "roster"
        "divider"
        "notice"
        "sheet";
    }

    /* The two lists side by side, each the pane's height and scrolling on its
       own. */
    aside {
      flex-direction: row;
    }

    tc-roster,
    tc-requests {
      flex: 1 1 0;
      min-width: 0;
      max-height: none;
    }

    .divider {
      width: auto;
      height: 6px;
      cursor: row-resize;
    }

    .divider::before {
      inset: calc(-1 * var(--reach)) 0;
    }
  }

  /* A railroad the apps did not build: its saved drawing is invalid, so it is
     drawn grey with nothing running on it (ADR-0085, decision 4). */
  tc-canvas.unbuilt {
    filter: grayscale(1);
    opacity: 0.45;
  }
`;
