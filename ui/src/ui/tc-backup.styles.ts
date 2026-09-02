import { css } from "lit";

/**
 * The backup dialog (`tc-backup`).
 *
 * Three registers, and they are the three the dialog is made of: what is
 * quietly true reads as a hint, what git said reads as itself, and a refusal
 * reads in the red that marks anything else that stopped
 * ([ADR-0024](../../../docs/adr/0024-the-drawing-shows-its-own-faults.md)).
 * git's words keep their own line breaks and a monospace face, because they
 * are quoted and not written here.
 *
 * A backup is a row that is chosen rather than one that acts where it is
 * clicked: restoring takes the press in the footer, so the row only has to
 * show which one the press is about.
 */
export const backupStyles = css`
  .root {
    margin: 0 0 0.4rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }

  .hint {
    margin: 0.2rem 0;
    color: var(--hint);
  }

  .waiting {
    margin: 0.2rem 0;
  }

  .needs {
    margin: 0.2rem 0;
    padding-left: 1.1rem;
    color: var(--unfinished);
  }

  .said,
  .wrong {
    margin: 0.5rem 0;
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85rem;
  }

  .wrong {
    color: var(--wrong);
  }

  .presses {
    display: flex;
    gap: 0.5rem;
    margin: 0.8rem 0 0.2rem;
  }

  h3 {
    margin: 1rem 0 0.4rem;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
  }

  ul.backups {
    margin: 0;
    padding: 0;
    list-style: none;
    max-height: 12rem;
    overflow-y: auto;
  }

  ul.backups button {
    display: grid;
    grid-template-columns: auto 1fr;
    column-gap: 0.6rem;
    width: 100%;
    padding: 0.25rem 0.3rem;
    border: none;
    border-radius: 3px;
    background: none;
    font: inherit;
    text-align: left;
    color: inherit;
    cursor: pointer;
  }

  ul.backups button:hover {
    background: color-mix(in srgb, var(--chosen) 8%, transparent);
  }

  ul.backups button.on {
    background: color-mix(in srgb, var(--chosen) 16%, transparent);
  }

  .when {
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  .what {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
`;
