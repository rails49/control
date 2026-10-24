import { css } from "lit";

import { symbols } from "./shared.styles.js";

/**
 * The palette pane (`tc-palette`): one tile per placeable kind, in groups.
 *
 * Drawn as the throttle panel is (`tc-driving.styles.ts`): each group a box on
 * the `--body` ground with a `--rule` border and round corners, as a function
 * button is, and a pressed tile tinted with `--chosen`, as a function that is
 * on is.
 */
export const paletteStyles = css`
  :host {
    display: block;
    padding: 10px;
  }

  h2 {
    margin: 2px 2px 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--hint);
  }

  /* One group of related symbols in a box of its own, two tiles to a row; a
     group of one takes the whole width, a block's 6x1 tile being as wide as
     the pane allows. */
  .group {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 2px;
    padding: 4px;
    border: 1px solid var(--rule);
    border-radius: 12px;
    background: var(--body);
  }

  .group.wide {
    grid-template-columns: 1fr;
  }

  .group + .group {
    margin-top: 10px;
  }

  /* A row's first tile goes to the left column, so a row of one leaves the
     right one empty rather than taking the next row's first tile. */
  button.first {
    grid-column: 1;
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
    border-radius: 9px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: grab;
    touch-action: none;
  }

  button:hover {
    background: color-mix(in srgb, var(--chosen) 9%, var(--body));
  }

  button:active {
    border-color: color-mix(in srgb, var(--chosen) 50%, transparent);
    background: color-mix(in srgb, var(--chosen) 18%, var(--body));
    cursor: grabbing;
  }

  button:focus-visible {
    outline: 2px solid var(--chosen);
    outline-offset: -2px;
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
    margin: 14px 2px 0;
    font-size: 11px;
    line-height: 1.9;
    color: var(--hint);
  }

  .hint + .hint {
    margin-top: 2px;
  }

  /* A key and what it does wrap as one. */
  .keys {
    display: flex;
    flex-wrap: wrap;
    gap: 0 10px;
  }

  .keys span {
    white-space: nowrap;
  }

  .hint kbd {
    padding: 1px 5px;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--body);
    color: var(--ink);
    font: 600 10px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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
