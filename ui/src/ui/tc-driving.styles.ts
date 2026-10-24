import { css, unsafeCSS } from "lit";

/** How far the track's travel stands in from its top and bottom, in CSS
 *  pixels: the thumb's half-height and some. A drag is read over the height
 *  between (`tc-driving.ts`). */
export const TRACK_PAD_PX = 18;

const PAD = unsafeCSS(`${TRACK_PAD_PX}px`);

/**
 * One train's driving controls (`tc-driving`), as
 * `docs/ui/images/throttle-mockup.html` draws a held panel (#968): the
 * picture across the top, the panel's full width at 16:9 with no margin, and
 * below it two columns — the clock, the blocks, the signal and the functions
 * on the left, and the speed, the slider and the button under it on the
 * right, where a right thumb holding a phone is. Only the functions scroll.
 * Where the panel sits and how big it is are the throttle view's
 * (`tc-throttle.styles.ts`).
 *
 * Colours are the page's, which follow the system's light or dark setting.
 * What lies over the picture is on the picture and not the page, so it is
 * light on a dark chip in either theme; the clock and the signal are pictures
 * of things on a railroad and keep their own colours.
 */
export const drivingStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }

  button {
    font: inherit;
  }

  /* The picture is the press that opens the train selector. It is shown
     whole, letterboxed in black as a screen is. */
  .view {
    position: relative;
    display: block;
    flex: none;
    width: 100%;
    aspect-ratio: 16 / 9;
    padding: 0;
    border: 0;
    overflow: hidden;
    background: black;
    color: inherit;
    cursor: pointer;
  }

  .thumbnail,
  .picture {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  /* No photo: a train, and its name under it. */
  .thumbnail.name {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: var(--body);
    color: var(--hint);
  }

  .thumbnail.name .icon {
    width: 64px;
    height: 64px;
  }

  .thumbnail.name span {
    color: var(--ink);
    font-size: 22px;
    font-weight: 700;
  }

  /* Laid over the picture: the train's name, LIVE and Trains. */
  .chip {
    position: absolute;
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 9px;
    border-radius: 999px;
    background: rgb(0 0 0 / 0.5);
    color: white;
    font-size: 12px;
    font-weight: 650;
    line-height: 1;
  }

  .chip svg {
    width: 14px;
    height: 14px;
  }

  .chip.title {
    left: 10px;
    bottom: 10px;
    border-radius: 7px;
    font-size: 13px;
  }

  .chip.live {
    top: 10px;
    left: 10px;
    font-size: 11px;
    letter-spacing: 0.08em;
  }

  .chip.live i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--red);
  }

  .chip.trains {
    top: 10px;
    right: 10px;
  }

  .lower {
    position: relative;
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) clamp(104px, 30%, 136px);
    gap: 12px;
    padding: 12px;
  }

  .left {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    min-height: 0;
  }

  /* The clock over the blocks, and the signal beside both. */
  .readout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 10px;
    align-items: start;
  }

  tc-clock {
    grid-column: 1;
    grid-row: 1;
    width: 64px;
    height: 64px;
  }

  .blocks {
    grid-column: 1;
    grid-row: 2;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 8px;
    align-items: center;
  }

  .label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--hint);
  }

  .block {
    justify-self: start;
    padding: 5px 8px;
    border: 1px solid var(--rule);
    border-radius: 7px;
    background: var(--body);
    color: var(--ink);
    font: 700 15px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  /* The two colours a route is lit in on the run view (ui/PANEL.md): green
     where the dispatcher holds the lock, cyan where the route is chosen. */
  .block.locked {
    border-color: color-mix(in srgb, var(--locked) 45%, transparent);
    background: color-mix(in srgb, var(--locked) 10%, transparent);
    color: var(--locked);
  }

  .block.committed {
    border-color: color-mix(in srgb, var(--committed) 45%, transparent);
    background: color-mix(in srgb, var(--committed) 10%, transparent);
    color: var(--committed);
  }

  .block.none {
    border-color: transparent;
    background: none;
    color: var(--hint);
    font-weight: 500;
  }

  .signal {
    grid-column: 2;
    grid-row: 1 / span 2;
    display: block;
    width: 50px;
    height: 156px;
  }

  .signal .mast {
    fill: var(--hint);
  }

  .signal .head {
    stroke: var(--rule);
    stroke-width: 3;
  }

  .functions {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    align-content: start;
  }

  button.function {
    position: relative;
    min-height: 50px;
    padding: 8px 10px;
    border: 1px solid var(--rule);
    border-radius: 12px;
    background: var(--body);
    color: var(--ink);
    font-size: 14px;
    line-height: 1.2;
    cursor: pointer;
  }

  /* A function that state/functions says is on. */
  button.function[aria-pressed="true"] {
    border-color: color-mix(in srgb, var(--chosen) 50%, transparent);
    background: color-mix(in srgb, var(--chosen) 18%, var(--body));
    font-weight: 650;
  }

  button.function[aria-pressed="true"]::after {
    content: "";
    position: absolute;
    top: 7px;
    right: 7px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--chosen);
  }

  .right {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
  }

  .reading {
    text-align: center;
    font-size: 36px;
    font-weight: 700;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: var(--ink);
  }

  .reading .unit {
    margin-left: 2px;
    font-size: 16px;
    color: var(--hint);
  }

  .motion {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 4px;
    color: var(--hint);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }

  .motion svg {
    width: 11px;
    height: 11px;
    color: var(--chosen);
  }

  /* Upright, 0 at the bottom, and the drag is the slider's, not the
     page's. --value is where it stands, 0 to 1. */
  .track {
    position: relative;
    flex: 1;
    min-height: 160px;
    overflow: hidden;
    border-radius: 16px;
    background: var(--rule);
    touch-action: none;
    cursor: grab;
  }

  .track .fill {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: calc(${PAD} + (100% - 2 * ${PAD}) * var(--value));
    background: color-mix(in srgb, var(--chosen) 20%, transparent);
  }

  /* 21 marks, every 5 %, longer toward the top; those at or below the value
     in the accent. */
  .track .tick {
    position: absolute;
    left: 50%;
    bottom: calc(${PAD} + (100% - 2 * ${PAD}) * var(--at) / 20 - 1px);
    width: calc(28% + 56% * var(--at) / 20);
    height: 2px;
    border-radius: 2px;
    background: var(--hint);
    transform: translateX(-50%);
  }

  .track .tick.lit {
    background: var(--chosen);
  }

  .track .thumb {
    position: absolute;
    left: 8px;
    right: 8px;
    bottom: calc(${PAD} + (100% - 2 * ${PAD}) * var(--value) - 12px);
    height: 24px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 3px;
    border-radius: 9px;
    background: var(--chosen);
  }

  .track .thumb i {
    display: block;
    width: 36%;
    height: 2px;
    margin: 0 auto;
    border-radius: 1px;
    background: var(--body);
    opacity: 0.7;
  }

  /* The one button under the slider: the stop while it is above 0, the
     reverser at 0. */
  button.go {
    flex: none;
    height: 64px;
    display: grid;
    place-items: center;
    border: 1px solid transparent;
    border-radius: 16px;
    cursor: pointer;
  }

  button.go svg {
    width: 30px;
    height: 30px;
  }

  button.go.stop {
    background: var(--red);
    color: white;
  }

  button.go.reverser {
    border-color: var(--rule);
    background: var(--body);
    color: var(--chosen);
  }

  button:disabled {
    cursor: default;
  }

  /* The rails not live: what drives is dimmed, the readout stays readable,
     and why sits over the bottom of the lower area. */
  .dead .functions,
  .dead .right {
    opacity: 0.4;
    pointer-events: none;
  }

  .still {
    position: absolute;
    left: 12px;
    right: 12px;
    bottom: 12px;
    margin: 0;
    padding: 12px 14px;
    border: 1px solid var(--wrong);
    border-radius: 12px;
    background: var(--wrong-body);
    color: var(--ink);
    font-size: 14px;
    font-weight: 650;
    text-align: center;
  }
`;
