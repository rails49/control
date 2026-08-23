import { css } from "lit";

/**
 * The roster pane (`tc-roster`): the trains the run has, one row each.
 *
 * It sits in the shell's left-pane slot, which the editor's palette sits in
 * too, so the width is the shell's (`--pane`) and not declared here
 * ([#169](https://github.com/rails49/control/issues/169)).
 *
 * A row is a name, where the train is, and how long it is: three columns, so
 * the blocks read down the pane rather than sitting wherever the name before
 * them ended. The length is right-aligned and tabular, being the one number.
 *
 * A row is also something to pick up — a drag onto a block places the train
 * ([#170](https://github.com/rails49/control/issues/170)) — so it takes the
 * grab cursor while the run is held and none while it is running. A train off
 * the layout is dimmed rather than hidden: it is on the roster, which is what
 * the pane lists.
 */
export const rosterStyles = css`
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

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: grid;
    grid-template-columns: 1fr auto;
    column-gap: 0.5rem;
    align-items: baseline;
    padding: 0.25rem 0.2rem;
    cursor: grab;
    touch-action: none; /* a drag on a touch screen is a drag, not a scroll */
    user-select: none;
  }

  li + li {
    border-top: 1px solid var(--rule);
  }

  /* No drag to start: the run is running, or there is no session at all. */
  li.still {
    cursor: default;
  }

  li.held {
    background: var(--rule);
  }

  /* Off the layout: on the roster and not on the rails. */
  li.off .name {
    color: var(--hint);
  }

  .name {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .length {
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  /* Where the train is, under its name: the block it stands in, or a phrase
     for a train that stands in none. */
  .where {
    grid-column: 1 / -1;
    font-size: 0.7rem;
    color: var(--hint);
  }

  .hint {
    margin: 0.8rem 0.2rem 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
