import { css } from "lit";

/**
 * The run view (`tc-panel`): the chrome round the drawing, laid out inside the
 * app's work row.
 *
 * The drawing itself is `tc-canvas`'s, in run mode, so everything that paints
 * a symbol, a wire, a route or a train is declared there and not here
 * ([#168](https://github.com/rails49/control/issues/168)).
 *
 * The roster fills the shell's left-pane slot, whose width is the shell's
 * (`--pane`), and the pane takes the full height of the work row: it is the
 * same rectangle the editor's palette occupies, so a toggle does not move the
 * pane under the pointer ([#169](https://github.com/rails49/control/issues/169)).
 * The request list sits directly under the roster in the same pane (#829,
 * #895).
 */
export const panelStyles = css`
  :host {
    display: grid;
    grid-template-columns: var(--pane) 1fr;
    grid-template-rows: auto 1fr;
    grid-template-areas:
      "roster notice"
      "roster sheet";
  }

  aside {
    grid-area: roster;
    border-right: 1px solid var(--rule);
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  /* Each list is its content's height, capped at half the pane, so the
     requests sit directly under the trains and the space left over is below
     them (#895). */
  tc-roster {
    flex: 0 1 auto;
    max-height: 50%;
    overflow-y: auto;
  }

  tc-requests {
    flex: 0 1 auto;
    max-height: 50%;
    overflow-y: auto;
    border-top: 1px solid var(--rule);
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
  }

  /* A grid so the canvas fills the row: it is a block element and takes the
     cell's height, which is what a viewport it can be fitted to needs. */
  main {
    grid-area: sheet;
    display: grid;
    overflow: hidden;
    min-height: 0;
  }
`;
