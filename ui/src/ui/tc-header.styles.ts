import { css } from "lit";

import { dismiss, menuBox, menuRow, menuRowChosen } from "./shared.styles.js";

/**
 * The band across the top (`tc-header`): what is true of the whole system, and
 * the two controls that act on it — the railroad picker at the left and the
 * view toggle at the right. The spacer parts what is loaded from what is going
 * on, and the rest is text.
 */
export const headerStyles = css`
  :host {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    padding: 0.3rem 0.6rem;
    border-bottom: 1px solid var(--rule);
  }

  ${dismiss}

  /* The picker's list hangs off the name, so the name is what it is
     positioned against, and both sit above the overlay that dismisses it. */
  .picker {
    position: relative;
    z-index: 12;
  }

  .chosen {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.15rem 0.4rem;
    border: none;
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .chosen:hover:not(:disabled) {
    background: #f0eeea;
  }

  /* Nothing to pick, so the name is text again and reads as text. */
  .chosen:disabled {
    cursor: default;
  }

  menu.drawings {
    position: absolute;
    top: calc(100% + 0.2rem);
    left: 0;
    z-index: 13;
    min-width: 10rem;
    ${menuBox}
  }

  menu.drawings li button {
    ${menuRow}
  }

  ${menuRowChosen}

  /* A name is one word however long it is, and never wraps. */
  .label {
    flex: 1;
    white-space: nowrap;
  }

  .tick {
    width: 16px;
  }

  .more {
    color: var(--hint);
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

  /* What the app talks to, and what it could not do. One row with room in it:
     per-container and hardware reachability land here (2a-docker), and the
     slot is where they go. */
  .health {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    min-width: 0;
  }

  .boundary {
    color: var(--hint);
    font-variant-numeric: tabular-nums;
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

  /* Trains on the layout freeze the drawing (ADR-0038, #169). The other thing
     the band says about the drawing itself, and the quieter of the two: a
     frozen drawing is the ordinary state of a railroad with trains on it, and
     nothing is wrong with it. So it reads as the boundary does and not as the
     refusal above. */
  .frozen {
    flex: none;
    color: var(--hint);
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

  /* Whether a train may move at all. Power on is the quiet case and reads as
     the boundary beside it does; the two ways of standing still are the
     operator's to act on, so they take the alarm the trouble beside them
     takes. */
  .power.on {
    color: var(--hint);
  }

  .power.stopped,
  .power.off {
    flex: none;
    padding: 0 0.35rem;
    border-radius: 0.2rem;
    background: var(--wrong-body);
    color: var(--wrong);
  }

  /* The view toggle: square around its icon, as the bar's tools are. */
  .view {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 1.9rem;
    height: 1.6rem;
    border: none;
    border-radius: 4px;
    background: none;
    color: inherit;
    cursor: pointer;
  }

  .view:hover {
    background: #f0eeea;
  }
`;
