import { css } from "lit";

import { heading } from "./shared.styles.js";

/**
 * The roster pane (`tc-roster`): the trains the run has, one row each.
 *
 * It sits in the run view's pane, whose size is the view's
 * (`tc-panel.styles.ts`) and not declared here.
 *
 * A row is the photo of the train's first locomotive, its name, where it is,
 * and how long it is. The photo sits in a slot of its own down the left, the
 * same size whether or not there is a picture in it, so the names line up
 * (#1012). A long name wraps onto a second line and is not cut short. The
 * blocks read down the pane rather than sitting wherever the name before them
 * ended. The length is right-aligned and tabular, being
 * the one number. A row's note about where the loaded timetable starts is a
 * line of its own under where the train is.
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

  ${heading}

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: grid;
    grid-template-columns: 3.2rem 1fr auto;
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

  /* No drag to start: there is no session at all. */
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

  /* The locomotive's photo, or an empty slot of the same size. */
  .photo {
    grid-row: 1 / span 2;
    align-self: center;
    display: block;
    width: 3.2rem;
    height: 1.8rem;
    object-fit: contain;
    -webkit-user-drag: none;
  }

  .name {
    overflow-wrap: anywhere;
  }

  .length {
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  /* Where the train is, under its name: the block it stands in, or a phrase
     for a train that stands in none. */
  .where {
    grid-column: 2 / -1;
    font-size: 0.7rem;
    color: var(--hint);
  }

  /* Why the last placement was refused, in place of where the train is: red,
     as a rejected request's reason is on the drawing. */
  .where.refused {
    color: var(--red);
  }

  /* Where the train is not where the loaded timetable starts, under where it
     is (#1357). */
  .note {
    grid-column: 2 / -1;
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
