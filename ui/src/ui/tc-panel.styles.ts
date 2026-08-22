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
 * (`--pane`), and takes the full height of the work row: it is the same
 * rectangle the editor's palette occupies, so a toggle does not move the pane
 * under the pointer ([#169](https://github.com/rails49/control/issues/169)).
 */
export const panelStyles = css`
  :host {
    display: grid;
    grid-template-columns: var(--pane) 1fr;
    grid-template-rows: auto 1fr;
    grid-template-areas:
      "roster session"
      "roster sheet";
  }

  tc-roster {
    grid-area: roster;
    border-right: 1px solid var(--rule);
    overflow-y: auto;
  }

  header {
    grid-area: session;
    display: flex;
    gap: 0.5rem;
    align-items: center;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--rule);
  }

  header .spacer {
    flex: 1;
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
