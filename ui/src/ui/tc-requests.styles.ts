import { css } from "lit";

/**
 * The request list (`tc-requests`): one row per request the dispatcher holds,
 * in the order it serves them (#829).
 *
 * It sits under the roster in the run view's left pane, so its width is the
 * shell's (`--pane`). A row is the train and its state on one line, where the
 * request goes from and to under them, which train it waits for under that
 * where the dispatcher refused it one (#1114), and the cancel at the right. A waiting
 * row takes the grab cursor, being something to drag into another place; an
 * underway one takes none, having started.
 */
export const requestsStyles = css`
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
    grid-template-columns: 1fr auto auto;
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

  li.still {
    cursor: default;
  }

  li.held {
    background: var(--rule);
  }

  .train {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .state {
    font-size: 0.7rem;
    color: var(--hint);
  }

  li.underway .state {
    color: inherit;
  }

  .cancel {
    grid-row: 1 / span 2;
    grid-column: 3;
    align-self: center;
    border: none;
    background: none;
    color: var(--hint);
    font: inherit;
    cursor: pointer;
    padding: 0 0.2rem;
  }

  .cancel:hover {
    color: inherit;
  }

  /* From and to, under the train. */
  .way {
    grid-column: 1 / 3;
    font-size: 0.7rem;
    color: var(--hint);
  }

  /* Which train it waits for, a line per sentence, under from and to. */
  .note {
    grid-column: 1 / 3;
    font-size: 0.7rem;
    font-style: italic;
  }

  .hint {
    margin: 0.8rem 0.2rem 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
