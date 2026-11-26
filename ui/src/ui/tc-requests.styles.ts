import { css } from "lit";

import { heading } from "./shared.styles.js";

/**
 * The list under the roster (`tc-requests`): the loaded timetable's entries
 * and the requests the dispatcher holds (#829, #1356).
 *
 * It sits in the run view's pane, under the roster or beside it, and its
 * size is the view's (`tc-panel.styles.ts`). The heading is "Timetable",
 * then the loaded timetable's name, then the controls the run view puts in
 * its slot, on a line of their own where one line does not hold them (#1357).
 * The heading's first line is the roster's heading's height (#1390). The
 * heading keeps its height and stays in view, and the rows scroll under it in
 * what is left of the list's height.
 *
 * A request's row is the train and its state
 * on one line, where the
 * request goes from and to under them, which train it waits for under that
 * where the dispatcher refused it one (#1114), and the cancel at the right,
 * with "arrived" before it on an underway row without sensors (#1323). A
 * long train name wraps onto a second line and is not cut short. A waiting
 * row takes the grab cursor, being something to drag into another place; an
 * underway one takes none, having started.
 *
 * An entry's row is laid out as a request's is, with no buttons. Its time
 * starts the second line, before where it goes, so the first line is as wide
 * as it is without a timetable. A row that is done is dimmed. A row that is
 * not picked up scrolls the list under a finger.
 *
 * An entry's dwell and description are in its row and not shown. Where the
 * list is 24rem wide or more they are shown, each on a line under where the
 * entry goes. The width is the list's own, read with a container query, since
 * a person sets the pane's width (#1344).
 *
 * An entry's open row (`tc-entry`, #1358) is the last thing in its row and as
 * wide as the row. A done row is not dimmed while it is open.
 */
export const requestsStyles = css`
  :host {
    container-type: inline-size;
    display: flex;
    flex-direction: column;
    padding: 0.4rem;
  }

  ${heading}

  .name {
    font-size: 0.75rem;
    overflow-wrap: anywhere;
  }

  ul {
    min-height: 0;
    overflow-y: auto;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* The time's column is as wide as the time, and only the second line has
     anything in it: the train's name starts at the row's left edge. */
  li {
    display: grid;
    grid-template-columns: [time] auto [train] 1fr [state] auto [arrived] auto [cancel] auto;
    column-gap: 0.5rem;
    align-items: baseline;
    padding: 0.25rem 0.2rem;
    cursor: grab;
    touch-action: none; /* a drag on a touch screen is a drag, not a scroll */
    -webkit-user-select: none; /* the rule Safari stops selecting for (#1312) */
    user-select: none;
    -webkit-touch-callout: none;
  }

  li + li {
    border-top: 1px solid var(--rule);
  }

  li.still {
    cursor: default;
    touch-action: auto;
  }

  li.held {
    background: var(--rule);
  }

  li.done {
    opacity: 0.5;
  }

  /* An open row is not dimmed. */
  li.done:has(tc-entry) {
    opacity: 1;
  }

  .train {
    grid-column: time / state;
    overflow-wrap: anywhere;
  }

  .state {
    grid-column: state;
    font-size: 0.7rem;
    color: var(--hint);
  }

  li.underway .state {
    color: inherit;
  }

  .arrived,
  .cancel {
    grid-row: 1 / span 2;
    align-self: center;
    border: none;
    background: none;
    color: var(--hint);
    font: inherit;
    cursor: pointer;
    padding: 0 0.2rem;
  }

  .arrived {
    grid-column: arrived;
    font-size: 0.7rem;
  }

  .cancel {
    grid-column: cancel;
  }

  .arrived:hover,
  .cancel:hover {
    color: inherit;
  }

  /* An entry's time, at the start of the line under the train. */
  .time {
    grid-column: time;
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
  }

  /* From and to, under the train, after the time where the row has one. */
  .way {
    grid-column: time / arrived;
    font-size: 0.7rem;
    color: var(--hint);
  }

  .time + .way {
    grid-column: train / arrived;
  }

  /* An entry's dwell and description, under where it goes. Not shown in a
     narrow list. */
  .dwell,
  .description {
    display: none;
    grid-column: time / arrived;
    font-size: 0.7rem;
    color: var(--hint);
    overflow-wrap: anywhere;
  }

  @container (min-width: 24rem) {
    .dwell,
    .description {
      display: block;
    }
  }

  /* Which train it waits for, a line per sentence, under from and to. */
  .note {
    grid-column: time / arrived;
    font-size: 0.7rem;
    font-style: italic;
  }

  /* An entry's open row, under the rest of its row and across it. */
  tc-entry {
    grid-column: 1 / -1;
  }

  .hint {
    margin: 0.8rem 0.2rem 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
