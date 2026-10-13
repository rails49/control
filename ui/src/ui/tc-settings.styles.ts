import { css } from "lit";

/**
 * The settings dialog (`tc-settings`).
 *
 * A railroad is a row that acts where it is pressed, unlike a backup in
 * `tc-backup`, which is chosen and then restored from the footer: loading
 * one asks the bus and the row answers, so there is nothing to confirm. The
 * tick says which is loaded and the row under the pointer says which would
 * be asked for. A refusal reads as a hint beneath the list, as `tc-backup`
 * reads its own. The name field and the two presses that make a railroad sit
 * in one row beneath, the field taking the width the presses leave, and what
 * refused a name or a write reads under that row in the weight a thing wrong
 * reads in. The Box part reads the same way: its press, and beneath it why
 * it is dead or what the installation refused it with; asked once more, what
 * turning off costs and the two presses in a row beneath it.
 */
export const settingsStyles = css`
  h3 {
    margin: 0.6rem 0 0.3rem;
    font-size: 0.9rem;
  }

  h3:first-child {
    margin-top: 0;
  }

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

  .backup {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }

  /* What backup says without being asked: the band note's words, in the
     weight a thing missing reads in. */
  .note {
    color: var(--unfinished);
  }

  .box {
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
`;
