import { css } from "lit";

/**
 * The settings dialog (`tc-settings`).
 *
 * A railroad is a row that acts where it is pressed, unlike a backup in
 * `tc-backup`, which is chosen and then restored from the footer: loading
 * one asks the bus and the row answers, so there is nothing to confirm. The
 * tick says which is loaded and the row under the pointer says which would
 * be asked for. A refusal reads as a hint beneath the list, as `tc-backup`
 * reads its own.
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
`;
