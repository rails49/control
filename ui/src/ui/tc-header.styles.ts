import { css } from "lit";

import { dismiss, menuBox, menuRow, menuRowChosen } from "./shared.styles.js";

/**
 * What a fault reads as on a coloured band: a pale chip carrying its own
 * ground, rather than red text that fights the blue behind it. One block, worn
 * by the four things that are wrong in the same way — the store not answering,
 * a broker that is not, a name no drawing can wear, and rails that are dead.
 *
 * Here and not in shared.styles.ts: nothing lives in that module that fewer
 * than two component stylesheets wear (#132), and this is one sheet's.
 */
const alarm = css`
  padding: 0 0.35rem;
  border-radius: 0.2rem;
  background: var(--wrong-body);
  color: var(--wrong);
`;

/**
 * The band across the top (tc-header): what is true of the whole system, and
 * the controls that act on it — the railroad picker at the left and the three
 * track-power presses beside the reading they act on. The spacer parts what is
 * loaded from what is going on, and the rest is text. The view selector is the
 * rail's (ADR-0064).
 *
 * It is a coloured band and not a ruled row, as the occupancy UI's is. What
 * that costs is the palette: --hint and --lit are mixed for paper and read
 * as mud on blue. So the quiet weight here is the band's own ink at reduced
 * opacity, which follows --band wherever it goes, and the loud one is
 * alarm above — a chip carrying the ground it needs with it.
 */
export const headerStyles = css`
  :host {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    height: 2.6rem;
    padding: 0 0.6rem;
    box-sizing: border-box;
    background: var(--band);
    color: var(--band-ink);
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
    background: rgb(255 255 255 / 0.18);
  }

  /* Nothing to pick — the rails have power, or the store lists nothing — so
     the name is text again and reads as text. The button says why when it is
     hovered (ADR-0060). */
  .chosen:disabled {
    cursor: default;
  }

  /* The list itself is paper and not band: it hangs over the work, where the
     page's own ink and rules are what everything else is drawn in. */
  menu.drawings {
    color: var(--ink);
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
    opacity: 0.7;
  }

  .drawing {
    font-weight: 600;
  }

  /* The whole of the unsaved indicator, so it is the one mark here that has to
     catch an eye that is not looking for it. */
  .unsaved {
    margin-left: -0.3rem;
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

  .session {
    opacity: 0.75;
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
    ${alarm}
  }

  /* Trains on the layout freeze the drawing (ADR-0038, #169). The other thing
     the band says about the drawing itself, and the quieter of the two: a
     frozen drawing is the ordinary state of a railroad with trains on it, and
     nothing is wrong with it. So it reads as the session clock does and not as the
     refusal above. */
  .frozen {
    flex: none;
    opacity: 0.75;
  }

  /* One line, whatever the store said: the band's height is a row of the
     page's grid, and a wrapped message would take the wrap out of the canvas. */
  .trouble {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    ${alarm}
  }

  /* Whether the broker is answering: the one thing a live band says that a
     replay's does not. */
  .link.joined {
    opacity: 0.75;
  }

  .link.gone {
    ${alarm}
  }

  /* Whether a train may move at all. Power on is the quiet case and reads as
     the session clock beside it does; the two ways of standing still are the
     operator's to act on, so they take the alarm the trouble beside them
     takes. */
  .power.on {
    opacity: 0.75;
  }

  .power.stopped,
  .power.off {
    flex: none;
    ${alarm}
  }

  /* ON, STOP and OFF (ADR-0051). They read as the rail's HOLD/GO reads —
     short words in capitals — because they are the same kind of press about
     the same railroad, and they sit next to the reading they act on. STOP
     wears the alarm the reading beside it wears when it lands. */
  .supply {
    display: flex;
    flex: none;
    gap: 0.25rem;
    align-items: center;
  }

  button.press {
    padding: 0.1rem 0.45rem;
    border: 1px solid rgb(255 255 255 / 0.55);
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    font-size: 0.85em;
    letter-spacing: 0.04em;
    cursor: pointer;
  }

  button.press:hover:not(:disabled) {
    background: rgb(255 255 255 / 0.18);
  }

  button.press.stopped {
    border-color: var(--wrong-body);
    color: var(--wrong-body);
  }

  /* Nothing to command, or the press would be swallowed: a dead button and
     not a hidden one, so the row does not move under the hand. */
  button.press:disabled {
    opacity: 0.45;
    cursor: default;
  }

  /* The drain is outstanding, so the button says what it is waiting for
     rather than what it would do. */
  button.press.waiting {
    border-color: rgb(255 255 255 / 0.3);
  }
`;
