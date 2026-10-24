import { css } from "lit";

/**
 * One train's driving controls (`tc-driving`), as arrangement A
 * ([#852](https://github.com/rails49/control/issues/852)): what the train is
 * reading across the top, its picture whole below that, and below it two
 * columns — the reverser, the functions, Turn around and the clock on the
 * left, and the speed, the slider and STOP on the right, where a right thumb
 * holding a phone is. The slider stands upright, 0 at the bottom, and takes
 * the drag for itself rather than scrolling the page. Where it sits and how
 * wide it is are the throttle view's (`tc-throttle.styles.ts`).
 */
export const drivingStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    min-width: 0;
  }

  h2 {
    margin: 0;
    font-size: 1rem;
    color: var(--ink);
  }

  /* What the train is reading, and its picture below with nothing laid over
     it but LIVE: the picture is what a person drives by. */
  .top {
    border: 1px solid var(--rule);
    border-radius: 4px;
    overflow: hidden;
  }

  .thumbnail,
  .picture {
    display: block;
    width: 100%;
    max-height: 40vh;
    object-fit: contain;
  }

  /* No photo: the name stands in the picture's place. */
  .thumbnail.name {
    display: grid;
    place-items: center;
    min-height: 6rem;
    font-size: 1.4rem;
    color: var(--hint);
  }

  /* The camera car's live picture, in the thumbnail's place and its whole
     frame shown; the thumbnail shows again whenever the stream fails. */
  .picture {
    background: var(--body);
  }

  .live {
    position: absolute;
    left: 0.6rem;
    bottom: 0.4rem;
    padding: 0.1rem 0.4rem;
    border: 1px solid var(--wrong);
    border-radius: 3px;
    background: var(--body);
    color: var(--wrong);
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
  }

  .bar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 0.6rem;
    align-items: center;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--rule);
  }

  /* The picture is the press that opens the train selector. */
  .view {
    position: relative;
    display: block;
    width: 100%;
    min-height: 6rem;
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .stands {
    color: var(--hint);
  }

  .below {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 1rem;
  }

  .below .left {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.8rem;
  }

  .below .right {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
  }

  button:disabled {
    color: var(--hint);
    cursor: default;
  }

  /* Why nothing can be driven: the power, or a session that is not there. */
  .still {
    margin: 0;
    padding: 0.3rem 0.5rem;
    border-left: 3px solid var(--wrong);
    background: var(--wrong-body);
  }

  .reverser {
    display: flex;
  }

  .reverser button {
    padding: 0.3rem 0.8rem;
    border: 1px solid var(--rule);
    background: var(--body);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .reverser button + button {
    border-left: none;
  }

  .reverser button[aria-pressed="true"] {
    background: var(--rule);
    color: var(--ink);
  }

  .reading {
    font-size: 1.6rem;
    font-variant-numeric: tabular-nums;
  }

  .motion {
    font-size: 0.7rem;
    color: var(--hint);
  }

  /* Upright, 0 at the bottom, and the drag is the slider's, not the page's. */
  input.speed {
    writing-mode: vertical-lr;
    direction: rtl;
    width: 3rem;
    height: 14rem;
    touch-action: none;
  }

  /* The press that puts the slider to 0, weighted like the thing a hand goes
     for without looking. */
  button.stop {
    padding: 0.3rem 1rem;
    border: 1px solid var(--wrong);
    border-radius: 4px;
    background: var(--body);
    color: var(--wrong);
    font: inherit;
    letter-spacing: 0.06em;
    cursor: pointer;
  }

  button.turn {
    padding: 0.3rem 0.8rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .aspect {
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    color: var(--body);
  }

  .aspect.stop {
    background: var(--red);
  }

  .aspect.caution {
    background: var(--amber);
  }

  .aspect.clear {
    background: var(--green);
  }

  ol.ahead {
    display: flex;
    gap: 0.3rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* The two colours a route is lit in on the run view, in a row: green where
     the dispatcher holds the lock and the train may move, cyan where the
     claim has not been made yet (ui/PANEL.md). */
  ol.ahead li {
    padding: 0.1rem 0.5rem;
    border: 1px solid var(--committed);
    border-radius: 3px;
    color: var(--committed);
  }

  ol.ahead li.locked {
    border-color: var(--locked);
    color: var(--locked);
  }

  .functions {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
  }

  button.function,
  button.more {
    padding: 0.25rem 0.7rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
    font: inherit;
  }

  /* A function that state/functions says is on, drawn as the reverser's
     pressed side is. */
  button.function[aria-pressed="true"],
  button.more[aria-expanded="true"] {
    background: var(--rule);
    color: var(--ink);
  }

  .hint {
    margin: 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
