import { css } from "lit";

/**
 * The run view (`tc-panel`): the chrome round the drawing, laid out inside the
 * app's work row.
 *
 * The drawing itself is `tc-canvas`'s, in run mode, so everything that paints
 * a symbol, a wire, a route or a train is declared there and not here
 * ([#168](https://github.com/rails49/control/issues/168)).
 */
export const panelStyles = css`
  :host {
    display: grid;
    grid-template-rows: auto 1fr;
  }

  header {
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
    display: grid;
    overflow: hidden;
    min-height: 0;
  }
`;
