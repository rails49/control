import { css } from "lit";

import { GAP } from "../model/pane.js";

/**
 * `tc-gap`: a gap `GAP` across (`model/pane.ts`) in the gap colour, `--chosen` on hover and while
 * dragged. What takes the press is wider, and wider again under a finger, and
 * lies over the edges of the parts either side.
 */
export const gapStyles = css`
  :host {
    --reach: 0.3rem;

    display: block;
    position: relative;
    z-index: 1;
    background: var(--gap);
    touch-action: none; /* a drag on a touch screen is a drag, not a scroll */
  }

  @media (pointer: coarse) {
    :host {
      --reach: 0.7rem;
    }
  }

  :host([axis="x"]) {
    width: ${GAP}px;
    cursor: col-resize;
  }

  :host([axis="y"]) {
    height: ${GAP}px;
    cursor: row-resize;
  }

  div {
    position: absolute;
  }

  :host([axis="x"]) div {
    inset: 0 calc(-1 * var(--reach));
  }

  :host([axis="y"]) div {
    inset: calc(-1 * var(--reach)) 0;
  }

  :host(:hover),
  :host(:active) {
    background: var(--chosen);
  }
`;
