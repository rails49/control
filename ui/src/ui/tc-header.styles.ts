import { css } from "lit";

/**
 * What a fault reads as on a coloured band: a pale chip carrying its own
 * ground, rather than red text that fights the blue behind it. One block, worn
 * by everything that is wrong in the same way — the store not answering, a
 * broker that is not, a name no drawing can wear, a drawing that does not
 * derive, and what the hardware says is wrong with the supply (#602).
 *
 * Here and not in shared.styles.ts: nothing lives in that module that fewer
 * than two component stylesheets wear (#132), and this is one sheet's.
 */
const alarm = css`
  padding: 0 0.35rem;
  border-radius: 0.2rem;
  background: var(--stop);
  color: var(--stop-ink);
`;

/**
 * An alarm carrying a whole sentence: what the app could not do, and what the
 * hardware says is wrong with the supply. One line whatever it says — the
 * band's height is a row of the page's grid, and a wrapped message would take
 * the wrap out of the canvas — so a long one is cut off here and read whole by
 * hovering. The two wear it and the two coarse marks beside them do not: a
 * mark names nothing and never shrinks.
 */
const sentence = css`
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  ${alarm}
`;

/**
 * The band across the top (tc-header): what is true of the whole system, and
 * the controls that act on it — the gear that opens Settings and the three
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

  .drawing {
    font-weight: 600;
  }

  /* The whole of the unsaved indicator, so it is the one mark here that has to
     catch an eye that is not looking for it. */
  .unsaved {
    margin-left: -0.3rem;
  }

  /* What the app could not do, and how far the run has got. One row with room
     in it: per-container and hardware reachability land here (2a-docker), and
     the slot is where they go. Nothing that is going right is drawn in it
     (#517). */
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

  /* Track power freezes the drawing (ADR-0071). The other thing the band says
     about the drawing itself, and the quieter of the two: a frozen drawing is
     the ordinary state of a railroad with power on, and nothing is wrong with
     it. So it reads as the session clock does and not as the
     refusal above. */
  .frozen {
    flex: none;
    opacity: 0.75;
  }

  /* Backup that is not running, as a press that opens its dialog (#688).
     Quieter than the trouble beside it: nothing is failing this minute, and
     the railroad runs. */
  .backup {
    flex: none;
    font: inherit;
    color: inherit;
    background: none;
    border: 1px dashed currentColor;
    border-radius: 3px;
    padding: 0 0.4em;
    cursor: pointer;
  }

  /* What the app could not do, in the store's or the broker's words. */
  .trouble {
    ${sentence}
  }

  /* What the hardware says is wrong with the supply, in its own words
     (ADR-0050, #602). The same weight the trouble beside it wears, the two
     being wrong in the same way and differing only in whose: the app could
     not do something, or the railroad has a fault on it. */
  .fault {
    ${sentence}
  }

  /* The gear that opens Settings (ADR-0072): a glyph in the band's ink, as
     the rail's buttons are, before the presses it is not one of. */
  button.settings {
    display: flex;
    flex: none;
    align-items: center;
    padding: 0.2rem;
    border: none;
    border-radius: 4px;
    background: none;
    color: inherit;
    cursor: pointer;
  }

  button.settings:hover {
    background: rgb(255 255 255 / 0.18);
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

  /* STOP is told apart from its neighbours whatever the supply is doing: it is
     the press a hand reaches for without reading, and the one whose cost of
     being pressed late is a train on the floor. */
  button.press.stopped {
    border-color: var(--stop);
    color: var(--stop);
  }

  /* Where the supply stands, marked on the press that names it: the same mark
     the rail puts on the current view, and the whole of what the band says
     about track power since #517. */
  button.press.at {
    background: rgb(255 255 255 / 0.22);
    font-weight: 600;
  }

  /* STOP is the one that is somebody's to act on. Standing there is not a
     state to leave a railroad in, so the marked button wears the alarm the
     reading beside it used to wear. ON and OFF marked wear the plain mark
     above: red on the chrome is a stop or a fault and nothing else, and a
     supply switched off is neither — it is where the railroad rests and comes
     up (ADR-0054, #585). */
  button.press.stopped.at {
    background: var(--stop);
    border-color: var(--stop);
    color: var(--stop-ink);
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
