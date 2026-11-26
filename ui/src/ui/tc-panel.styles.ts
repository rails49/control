import { GAP_PX } from "@rails49/look";
import { css, unsafeCSS } from "lit";

import { DRAWING, LEAST, LIST, UPRIGHT } from "../model/pane.js";

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
 * corners, and the view's background is the gap colour (`--gap`), which shows
 * through the gaps between them.
 *
 * The divider between the pane and the drawing is a gap, `look-gap`
 * (rails49/look#62), clear at rest. It sets the pane's size. The view hands
 * it over as `--pane-size`, and until a person has dragged the divider the
 * width is the shell's `--pane`, which the editor's palette has. The size is
 * held to the limits a drag is held to (`model/pane.ts`) when the window
 * changes size.
 *
 * A second gap between the two lists sets the trains list's height, or its
 * width side by side (#1391). The view hands it over as `--lists-size`.
 * Until a person has dragged it the trains list is as tall as its rows up to
 * half the pane, or half the pane's width side by side. When the window
 * changes size the timetable list keeps its least.
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
    min-width: 0;
    min-height: 0;
  }

  /* The two look-gaps, by class: only where each sits is set here, and look
     draws the rest. */
  .pane {
    grid-area: divider;
  }

  .lists {
    flex: none;
  }

  /* The trains are the height the gap was dragged to, or until then their
     content's height capped at half the pane. The requests sit directly under
     them and take the rest (#895). */
  tc-roster {
    flex: 0 1 var(--lists-size, auto);
    max-height: min(var(--lists-size, 50%), 100% - ${LIST.left + GAP_PX}px);
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
       own: the trains as wide as the gap was dragged to, or until then half
       the pane, and the requests the rest. */
    aside {
      flex-direction: row;
    }

    tc-roster {
      flex: 0 1 var(--lists-size, calc(50% - ${GAP_PX / 2}px));
      min-width: 0;
      max-width: calc(100% - ${LIST.above + GAP_PX}px);
      max-height: none;
    }

    tc-requests {
      min-width: 0;
    }
  }

  /* A railroad the apps did not build: its saved drawing is invalid, so it is
     drawn grey with nothing running on it (ADR-0085, decision 4). */
  tc-canvas.unbuilt {
    filter: grayscale(1);
    opacity: 0.45;
  }
`;
