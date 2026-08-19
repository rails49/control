import { css } from "lit";

/**
 * The band both pages wear across the top (`tc-header`). It shows status and
 * nothing else, so it has no control in it to size — the spacer parts what is
 * open from what is going on, and the rest is text.
 */
export const headerStyles = css`
  :host {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    padding: 0.3rem 0.6rem;
    border-bottom: 1px solid var(--rule);
  }

  .drawing {
    font-weight: 600;
  }

  /* The whole of the unsaved indicator, so it is the one mark here that has to
     catch an eye that is not looking for it. */
  .unsaved {
    margin-left: -0.3rem;
    color: var(--lit);
  }

  .mode,
  .trace,
  .tick {
    color: var(--hint);
  }

  .tick {
    font-variant-numeric: tabular-nums;
    min-width: 4.5rem;
    text-align: right;
  }

  .spacer {
    flex: 1;
  }

  /* The one thing the band says about the drawing itself: coarse, so it is a
     mark and not a sentence. A pale ground rather than red text alone, or it
     would read as the first clause of the trouble beside it, which is the
     other party's mistake. It never shrinks; the sentence does. */
  .refused {
    flex: none;
    padding: 0 0.35rem;
    border-radius: 0.2rem;
    background: var(--wrong-body);
    color: var(--wrong);
  }

  /* One line, whatever the store said: the band's height is a row of the
     page's grid, and a wrapped message would take the wrap out of the canvas. */
  .trouble {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    color: var(--wrong);
  }

  /* Whether the bridge is answering: the one thing a live session's band says
     that a replay's does not. */
  .link.joined {
    color: var(--lit);
  }

  .link.gone {
    color: var(--wrong);
  }

  .other {
    color: var(--chosen);
    text-decoration: none;
  }

  .other:hover {
    text-decoration: underline;
  }
`;
