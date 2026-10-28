import { css } from "lit";

/**
 * The settings dialog (`tc-settings`): its tabs, the Backup tab drawn by
 * `tc-backup` and the others laid out as below.
 *
 * A railroad is a row that acts where it is pressed, unlike a backup in
 * `tc-backup`, which is chosen and then restored from the press beneath the
 * list: loading one asks the bus and the row answers, so there is nothing to confirm. The
 * tick says which is loaded and the row under the pointer says which would
 * be asked for. A refusal reads as a hint beneath the list, as `tc-backup`
 * reads its own. The name field and the two presses that make a railroad sit
 * in one row beneath, the field taking the width the presses leave, and what
 * refused a name or a write reads under that row in the weight a thing wrong
 * reads in. The Shutdown tab reads the same way: its press, and beneath it why
 * it is dead or what the installation refused it with; asked once more, what
 * turning off costs and the two presses in a row beneath it. A press waiting
 * for the track to go dead reads "stopping trains…" with the stop sign in a
 * row beside it. A pick on its way wears the spinner at the end of its
 * row, and one the layout did not answer says so there, in the weight a
 * thing missing reads in. A row's trash sits at its end, and pressed, the
 * row gives way to what deleting it costs and the two presses beside it.
 * The Points, Driving and Throttles tabs are narrow fields, the hints beneath
 * them.
 */
export const settingsStyles = css`
  .hint {
    margin: 0.2rem 0;
    color: var(--hint);
  }

  ul.railroads {
    margin: 0;
    padding: 0;
    list-style: none;
    max-height: 12rem;
    overflow-y: auto;
  }

  ul.railroads button {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    width: 100%;
    padding: 0.25rem 0.3rem;
    border: none;
    border-radius: 3px;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  /* A row is its press, and beside it the trash that deletes it (#1074). */
  ul.railroads li {
    display: flex;
    align-items: center;
  }

  ul.railroads button.delete {
    width: auto;
    flex: none;
  }

  /* A row whose Delete was pressed: what deleting it costs, and the two
     presses beside it. */
  ul.railroads li.deleting {
    flex-wrap: wrap;
    gap: 0.4rem;
    padding: 0.25rem 0.3rem;
  }

  ul.railroads li.deleting .asking {
    flex: 1;
  }

  ul.railroads button:hover:not(:disabled) {
    background: color-mix(in srgb, var(--chosen) 8%, transparent);
  }

  ul.railroads button:disabled {
    color: var(--hint);
    cursor: default;
  }

  /* A name is one word however long it is, and never wraps. */
  .label {
    flex: 1;
    white-space: nowrap;
  }

  .tick {
    width: 1rem;
  }

  ul.railroads sl-spinner {
    font-size: 0.9rem;
  }

  .unanswered {
    color: var(--unfinished);
    white-space: nowrap;
  }

  .making {
    display: flex;
    align-items: flex-end;
    gap: 0.4rem;
    margin-top: 0.5rem;
  }

  .making sl-input {
    flex: 1;
  }

  .wrong {
    color: var(--unfinished);
  }

  .points sl-input,
  .driving sl-input,
  .throttles sl-input {
    max-width: 14rem;
  }

  .shutdown {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.3rem;
  }

  .asking {
    margin: 0;
  }

  .presses {
    display: flex;
    gap: 0.4rem;
  }

  /* A press waiting on a dead track: "stopping trains…" with the stop sign
     beside it (ADR-0085, decision 5). */
  .stopping {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 0.3rem 0;
  }
`;
