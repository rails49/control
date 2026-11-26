import { css } from "lit";

/**
 * An entry's open row (`tc-entry`): a line for each of its time, its dwell
 * and its description, and Delete under them at the right (#1358).
 *
 * It is drawn inside the row of `tc-requests`, across the row's width. A
 * line is the field's name and the field. The time and the dwell are as wide
 * as what they hold, and the description takes the width left, so the row
 * fits the pane at its least width.
 *
 * The row round it is something to drag and lets no text be selected
 * (`tc-requests.styles.ts`). Here text is typed and selected, and the cursor
 * is the field's own.
 *
 * Under a finger a field's text is 16px: Safari zooms the page into a field
 * whose text is smaller when it takes the focus.
 */
export const entryStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    padding-top: 0.3rem;
    cursor: auto;
    -webkit-user-select: text;
    user-select: text;
  }

  label {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    font-size: 0.7rem;
    color: var(--hint);
  }

  label span:first-child {
    flex: none;
    width: 6.5em;
  }

  input {
    box-sizing: border-box;
    min-width: 0;
    padding: 0.15rem 0.3rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--paper);
    color: var(--ink);
    font: inherit;
    font-size: 0.8rem;
  }

  .at {
    width: 4.5em;
    font-variant-numeric: tabular-nums;
  }

  .dwell {
    width: 3.5em;
    font-variant-numeric: tabular-nums;
  }

  .description {
    flex: 1;
  }

  button {
    align-self: flex-end;
    padding: 0.15rem 0.5rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    font-size: 0.7rem;
    cursor: pointer;
  }

  @media (pointer: coarse) {
    input,
    button {
      font-size: 16px;
    }
  }
`;
