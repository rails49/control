import { css } from "lit";

/**
 * The controls in the list's heading (`tc-timetable-controls`, #1357): the
 * Record switch and Start, on one line.
 *
 * The element is a flex item of the heading it is put in and keeps to the
 * right of it. Where the heading is too narrow for the name and the controls
 * the heading wraps and the controls are a line of their own. The pane can be
 * 144px wide, so the controls wrap among themselves too.
 *
 * The switch is a track with a knob and the word beside it. On, the track is
 * the chosen colour and the knob is at its right.
 */
export const timetableControlsStyles = css`
  :host {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.2rem 0.5rem;
    margin-left: auto;
    font-size: 0.75rem;
  }

  /* The menu and the dialog lie over the page and are no items of the line. */
  tc-menu,
  tc-timetable-dialog {
    display: contents;
  }

  button {
    border: none;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
    padding: 0.15rem 0.3rem;
  }

  button:disabled {
    color: var(--hint);
    cursor: default;
  }

  .menu {
    min-width: 1.8rem;
    font-size: 1.1rem;
    line-height: 1;
  }

  .start {
    border: 1px solid var(--rule);
    border-radius: 3px;
  }

  .record {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
  }

  .record i {
    position: relative;
    width: 1.5rem;
    height: 0.9rem;
    border-radius: 999px;
    background: var(--rule);
  }

  .record i::before {
    content: "";
    position: absolute;
    top: 0.1rem;
    left: 0.1rem;
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 50%;
    background: var(--body);
    transition: transform 120ms;
  }

  .record[aria-checked="true"] i {
    background: var(--chosen);
  }

  .record[aria-checked="true"] i::before {
    transform: translateX(0.6rem);
  }

  .record:disabled i {
    opacity: 0.5;
  }

  @media (prefers-reduced-motion: reduce) {
    .record i::before {
      transition: none;
    }
  }
`;
