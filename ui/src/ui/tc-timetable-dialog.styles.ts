import { css } from "lit";

/**
 * The timetable menu's dialogs (`tc-timetable-dialog`, #1357).
 *
 * Load and Delete list the store's names one under the other, each a button
 * as wide as the dialog and at least 40px high, a thumb's target. What the
 * store refused with, and why a name will not do, is a red line under the
 * list or the field.
 */
export const timetableDialogStyles = css`
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li + li {
    border-top: 1px solid var(--rule);
  }

  .pick {
    width: 100%;
    min-height: 40px;
    padding: 0.3rem 0.5rem;
    border: none;
    border-radius: 3px;
    background: none;
    color: var(--ink);
    font: inherit;
    text-align: left;
    overflow-wrap: anywhere;
    cursor: pointer;
  }

  .pick:hover {
    background: var(--chosen);
    color: #fff;
  }

  .hint {
    margin: 0;
    color: var(--hint);
  }

  .trouble {
    margin: 0.75rem 0 0;
    color: var(--red);
  }
`;
