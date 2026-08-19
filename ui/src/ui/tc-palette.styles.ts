import { css } from "lit";

import { symbols } from "./shared.styles.js";

/** The palette pane (`tc-palette`): one tile per placeable kind. */
export const paletteStyles = css`
  :host {
    display: block;
    padding: 0.4rem;
  }

  h2 {
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
    margin: 0.3rem 0.2rem;
  }

  /* One group of related symbols, two tiles to a row; a group of one takes the
     whole width, a block's 6x1 tile being as wide as the pane allows. Space
     between the groups is the only thing telling them apart — the palette has
     no words in it and is not about to grow three headings. */
  .group {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.15rem;
  }

  .group.wide {
    grid-template-columns: 1fr;
  }

  .group + .group {
    margin-top: 1.3rem;
  }

  /* The tiles carry no names, so the symbol is centred in the tile rather than
     sitting at the head of a row of text. */
  button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.45rem 0.3rem;
    border: 1px solid transparent;
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: grab;
    touch-action: none;
  }

  button:hover {
    background: #f0eeea;
  }

  button:active {
    cursor: grabbing;
  }

  /* A tile keeps its symbol's own shape: the height is fixed and the width
     follows the footprint, so a block reads as the long thing it is instead of
     being letterboxed into a square. */
  svg {
    height: 2.3rem;
    width: auto;
    max-width: 100%;
    flex: none;
  }

  /* What the tiles cannot say: that they are dragged, and the keys that turn
     one on the way over. */
  .hint {
    margin: 0.8rem 0.2rem 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }

  .hint + .hint {
    margin-top: 0;
  }

  .hint kbd {
    font: inherit;
    color: var(--ink);
  }

  /* Definitions only, shared by every tile: sized to nothing so it takes no
     room, rather than hidden, which would take its contents out of reach. */
  svg.defs {
    position: absolute;
    width: 0;
    height: 0;
  }

  ${symbols}
`;
