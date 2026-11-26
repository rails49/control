import { css } from "lit";

import { columnHeading, heading } from "./shared.styles.js";

/**
 * The list under the roster (`tc-requests`): the loaded timetable's entries
 * and the requests the dispatcher holds (#829, #1356).
 *
 * It sits in the run view's pane, under the roster or beside it, and its
 * size is the view's (`tc-panel.styles.ts`). The heading is "Timetable",
 * then the loaded timetable's name, then the controls the run view puts in
 * its slot, on a line of their own where one line does not hold them (#1357).
 * The heading's first line is the roster's heading's height (#1390). The
 * heading keeps its height and stays in view, and the table scrolls under it
 * in what is left of the list's height.
 *
 * The rows are a table (#1393): columns Time, Train, To, Dwell, Description,
 * State and the action, under a row of column headings that stays at the top
 * of what scrolls. Every row takes the table's columns (CSS subgrid), so the
 * cells line up with the headings. A row is one line. The Train column is at
 * most 30% of the table's width; a longer train name wraps in its cell and is
 * not cut short. A row the list scrolls to stops under the headings. A refused request's "waits for" line is
 * under its row, from the Train column to the right edge. An entry's open row
 * (`tc-entry`, #1358) is under its row, across the table.
 *
 * Every other row takes the stripe shade, with its "waits for" line and its
 * open row, and no line divides two rows. A row that is done is dimmed. A row
 * picked up is marked, over its stripe. A done row is not dimmed while it is
 * open. A waiting row takes the grab cursor, being something to drag into
 * another place; any other row takes none. A row that is not picked up
 * scrolls the list under a finger.
 *
 * Dwell and Description, headings and cells, are in the markup at any width
 * and shown where the list is 34rem wide or more, the table having their
 * columns only there. The width is the list's own, read with a container
 * query, since a person sets the pane's width (#1344).
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

  .table {
    min-height: 0;
    overflow-y: auto;
    display: grid;
    grid-template-columns: [time] auto [train] fit-content(30%) [way] 1fr [state] auto [action] auto;
    align-content: start;
    column-gap: 0.5rem;
    scroll-padding-top: 1.4rem; /* a row scrolled to is not under the headings */
  }

  .columns {
    ${columnHeading}
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: subgrid;
    position: sticky;
    top: 0;
    z-index: 1;
    padding-inline: 0.2rem;
  }

  ul {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: subgrid;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: subgrid;
    align-items: baseline;
    padding: 0.25rem 0.2rem;
    cursor: grab;
    touch-action: none; /* a drag on a touch screen is a drag, not a scroll */
    -webkit-user-select: none; /* the rule Safari stops selecting for (#1312) */
    user-select: none;
    -webkit-touch-callout: none;
  }

  li:nth-child(even) {
    background: var(--stripe);
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

  .time {
    grid-column: time;
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
  }

  .train {
    grid-column: train;
    overflow-wrap: anywhere;
  }

  .way {
    grid-column: way;
    font-size: 0.7rem;
  }

  .state {
    grid-column: state;
    font-size: 0.7rem;
    color: var(--hint);
  }

  li.underway .state {
    color: inherit;
  }

  .action {
    grid-column: action;
    align-self: center;
    display: flex;
  }

  .arrived,
  .cancel {
    border: none;
    background: none;
    color: var(--hint);
    font: inherit;
    cursor: pointer;
    padding: 0 0.2rem;
  }

  .arrived {
    font-size: 0.7rem;
  }

  .arrived:hover,
  .cancel:hover {
    color: inherit;
  }

  /* Not shown in a narrow list. */
  .dwell,
  .description {
    display: none;
    font-size: 0.7rem;
    color: var(--hint);
    overflow-wrap: anywhere;
  }

  .dwell {
    grid-column: dwell;
  }

  .description {
    grid-column: description;
  }

  @container (min-width: 34rem) {
    .table {
      grid-template-columns:
        [time] auto [train] fit-content(30%) [way] 1fr [dwell] auto [description] 1fr
        [state] auto [action] auto;
    }

    .dwell,
    .description {
      display: block;
    }
  }

  /* Which train it waits for, a line per sentence, under the row from the
     Train column on. */
  .note {
    grid-column: train / -1;
    font-size: 0.7rem;
    font-style: italic;
  }

  /* An entry's open row, under the rest of its row and across it. */
  tc-entry {
    grid-column: 1 / -1;
  }

  .hint {
    grid-column: 1 / -1;
    margin: 0.8rem 0.2rem 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
