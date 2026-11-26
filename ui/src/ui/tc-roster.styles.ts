import { css } from "lit";

import { heading } from "./shared.styles.js";

/**
 * The roster pane (`tc-roster`): the trains the run has, as a table, one row
 * each (#1392).
 *
 * It sits in the run view's pane, whose size is the view's
 * (`tc-panel.styles.ts`) and not declared here. The pane scrolls, and the
 * heading bar and the column heading row under it stay in view while the
 * rows scroll.
 *
 * A row is the photo of the train's first locomotive, its name, where it is,
 * where the loaded timetable starts it, and how long it is. The photo sits in
 * a slot of its own, the same size whether or not there is a picture in it,
 * so the names line up (#1012). A row is as tall as that slot. A long name
 * wraps inside its cell and is not cut short. The length is right-aligned and
 * tabular, being the one number. The start cell is in the hint colour where
 * the train is in its start block and in red where it is not, or is there
 * facing the other way. Rows are striped, with no rule between them.
 *
 * A row is also something to pick up — a drag onto a block places the train
 * ([#170](https://github.com/rails49/control/issues/170)) — so it takes the
 * grab cursor while a session is joined. The held row's mark wins over the
 * stripe. A train off the layout is dimmed rather than hidden: it is on the
 * roster, which is what the pane lists.
 */
export const rosterStyles = css`
  :host {
    display: block;
    padding: 0.4rem;
  }

  ${heading}

  header {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--paper);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th {
    position: sticky;
    top: 2rem; /* under the heading bar, whose height is the shared one */
    padding: 0 0.25rem 0.2rem;
    background: var(--paper);
    font-size: 0.7rem;
    font-weight: bold;
    text-align: left;
    color: var(--hint);
  }

  td {
    height: 1.8rem;
    padding: 0 0.25rem;
    vertical-align: middle;
  }

  tbody tr {
    cursor: grab;
  }

  /* A table row takes no touch-action, so the drag's rules are on its cells. */
  tbody td {
    touch-action: none; /* a drag on a touch screen is a drag, not a scroll */
    -webkit-user-select: none; /* the rule Safari stops selecting for (#1312) */
    user-select: none;
    -webkit-touch-callout: none;
  }

  tbody tr:nth-child(even) {
    background: var(--stripe);
  }

  /* No drag to start: there is no session at all. */
  tbody tr.still {
    cursor: default;
  }

  tbody tr.held {
    background: var(--rule);
  }

  /* Off the layout: on the roster and not on the rails. */
  tr.off .name {
    color: var(--hint);
  }

  /* The locomotive's photo, or an empty slot of the same size. */
  .photo {
    display: block;
    width: 3.2rem;
    height: 1.8rem;
    object-fit: contain;
    -webkit-user-drag: none;
  }

  .name {
    width: 100%;
    overflow-wrap: anywhere;
  }

  .length {
    text-align: right;
    white-space: nowrap;
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  /* Where the train is: the block it stands in, or a phrase for a train that
     stands in none. */
  .where {
    white-space: nowrap;
    color: var(--hint);
  }

  /* Why the last placement was refused, in place of where the train is: red,
     as a rejected request's reason is on the drawing. */
  .where.refused {
    white-space: normal;
    color: var(--red);
  }

  .start {
    white-space: nowrap;
    color: var(--hint);
  }

  .start.missed,
  .start.turned {
    color: var(--red);
  }

  .hint {
    margin: 0.8rem 0.2rem 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
