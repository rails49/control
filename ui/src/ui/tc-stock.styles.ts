import { css } from "lit";

/**
 * The stock view (`tc-stock`), as
 * [stock-mockup.html](../../../docs/ui/images/stock-mockup.html) lays it out
 * and in the throttle's visual style (ui/STOCK.md, #978): a bar across the
 * top, and under it the list, `minmax(300px, 380px)`, beside the editor of the
 * item chosen in it.
 *
 * **Not the shell's left-pane slot.** `--pane` is the width of the strip
 * beside a drawing surface — the editor's palette, the run view's roster
 * ([#169](https://github.com/rails49/control/issues/169)) — and this view has
 * no surface, so it declares its own columns and leaves `--pane` alone.
 *
 * **One column where the view is narrower than 760 px**, read off the view's
 * own width with a container query rather than the window's: the list, and a
 * pressed card replaces it with the editor, which then has a back button.
 *
 * **Every photo is shown whole** (`object-fit: contain`) in a frame 10:3 wide:
 * train cars are wide and low, and a crop would cut off the end that tells
 * two of them apart.
 *
 * A control the length guard has killed keeps its box and takes the hint
 * colour, with the reason beside it — a field that vanished while track power
 * was on would leave a person looking for it (ui/STOCK.md#the-length-guard).
 */
export const stockStyles = css`
  :host {
    container-type: inline-size;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    background: var(--paper);
    color: var(--ink);
  }

  button,
  input,
  select,
  textarea {
    font: inherit;
    color: inherit;
  }

  button:focus-visible,
  label.choose:focus-within {
    outline: 2px solid var(--chosen);
    outline-offset: 2px;
  }

  /* --- the bar --- */

  .bar {
    flex: none;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--rule);
    background: var(--body);
  }

  .bar h1 {
    margin: 0;
    font-size: 17px;
    font-weight: 700;
  }

  .bar .railroad {
    flex: 1;
    min-width: 0;
    color: var(--hint);
    font-family: ui-monospace, monospace;
    font-size: 13px;
  }

  .said {
    min-width: 0;
    color: var(--hint);
    font-size: 13px;
    text-align: right;
  }

  .said.trouble {
    color: var(--wrong);
    font-weight: 600;
  }

  .said.waits {
    color: var(--lit);
    font-weight: 600;
  }

  .said.landed {
    color: var(--chosen);
    font-weight: 600;
  }

  button.save {
    flex: none;
    height: 40px;
    padding: 0 20px;
    border: 0;
    border-radius: 12px;
    background: var(--chosen);
    color: var(--body);
    font-size: 15px;
    font-weight: 650;
    cursor: pointer;
  }

  button.save:disabled {
    border: 1px solid var(--rule);
    background: var(--paper);
    color: var(--hint);
    cursor: default;
  }

  /* --- the two columns --- */

  .cols {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
    gap: 16px;
    padding: 16px;
  }

  section.list,
  section.editor {
    min-height: 0;
    border: 1px solid var(--rule);
    border-radius: 20px;
    background: var(--body);
  }

  section.list {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  section.editor {
    position: relative;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  button.back {
    display: none;
  }

  @container (max-width: 759px) {
    .cols {
      grid-template-columns: minmax(0, 1fr);
      padding: 0;
      gap: 0;
    }

    section.list,
    section.editor {
      border: 0;
      border-radius: 0;
    }

    .cols.editing section.list,
    .cols:not(.editing) section.editor {
      display: none;
    }

    button.back {
      display: grid;
    }

    .grid {
      grid-template-columns: minmax(0, 1fr);
    }

    li.function {
      grid-template-columns: 64px minmax(0, 1fr) 36px;
    }

    li.function .seg {
      grid-column: 1 / -2;
      grid-row: 2;
    }
  }

  /* --- the list --- */

  .tabs {
    flex: none;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    margin: 14px 14px 10px;
    padding: 3px;
    border-radius: 12px;
    background: var(--rule);
  }

  button.tab {
    height: 38px;
    border: 0;
    border-radius: 9px;
    background: transparent;
    color: var(--hint);
    font-size: 14px;
    font-weight: 650;
    cursor: pointer;
  }

  button.tab[aria-selected="true"] {
    background: var(--body);
    color: var(--ink);
  }

  .count {
    margin-left: 5px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }

  .head {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 0 14px 10px;
  }

  .head p {
    margin: 0;
    color: var(--hint);
    font-size: 12.5px;
  }

  .cards {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 2px 14px 14px;
  }

  button.card {
    display: grid;
    grid-template-columns: 132px minmax(0, 1fr);
    align-items: center;
    gap: 12px;
    padding: 6px;
    border: 1px solid var(--rule);
    border-radius: 14px;
    background: var(--paper);
    text-align: left;
    cursor: pointer;
  }

  button.card[aria-current="true"] {
    border-color: var(--chosen);
    box-shadow: 0 0 0 1.5px var(--chosen);
    background: var(--body);
  }

  .frame,
  .photo-frame {
    position: relative;
    display: block;
    width: 100%;
    aspect-ratio: 10 / 3;
    overflow: hidden;
    background: var(--rule);
  }

  .frame {
    border-radius: 9px;
  }

  .frame img,
  .photo-frame img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: var(--track);
  }

  .no-photo {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--hint);
    font-size: 12px;
    font-weight: 600;
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }

  .text .name {
    overflow: hidden;
    font-size: 15px;
    font-weight: 700;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .facts {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 8px;
    color: var(--hint);
    font-size: 12px;
  }

  .pill {
    padding: 2px 6px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--body);
    color: var(--ink);
    font: 650 11.5px/1.2 ui-monospace, monospace;
  }

  /* --- the editor --- */

  .ed-head {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 20px;
    border-bottom: 1px solid var(--rule);
    background: var(--body);
  }

  .title {
    flex: 1;
    min-width: 0;
  }

  .eyebrow,
  .label,
  h3 {
    margin: 0;
    color: var(--hint);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .ed-head h2 {
    margin: 1px 0 0;
    overflow: hidden;
    font-size: 21px;
    font-weight: 700;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  button.back {
    flex: none;
    width: 40px;
    height: 40px;
    place-items: center;
    padding: 0;
    border: 1px solid var(--rule);
    border-radius: 50%;
    background: var(--paper);
    font-size: 20px;
    cursor: pointer;
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: 22px;
    max-width: 760px;
    padding: 18px 20px 28px;
  }

  .empty {
    display: grid;
    place-items: center;
    height: 100%;
    padding: 40px;
    color: var(--hint);
    text-align: center;
  }

  .photo-frame {
    border-radius: 16px;
  }

  .photo-frame.empty {
    display: grid;
    place-items: center;
    box-sizing: border-box;
    border: 2px dashed var(--rule);
    background: var(--paper);
    color: var(--hint);
  }

  .photo-frame.hot {
    border: 2px dashed var(--chosen);
  }

  .drop {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 12px;
    font-size: 14px;
    text-align: center;
  }

  .drop b {
    color: var(--ink);
    font-size: 16px;
  }

  .wait {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    background: color-mix(in srgb, var(--track) 45%, transparent);
    color: var(--body);
    font-weight: 650;
  }

  .photo-tools,
  .row-end {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 10px;
  }

  .photo-tools {
    margin-top: -12px;
  }

  label.choose,
  button.take,
  button.new,
  button.new-car,
  button.add-function,
  button.delete {
    position: relative;
    display: inline-flex;
    align-items: center;
    height: 38px;
    padding: 0 14px;
    border: 1px solid var(--rule);
    border-radius: 10px;
    background: var(--paper);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }

  button.new,
  button.new-car,
  button.add-function {
    height: 32px;
    padding: 0 10px;
    font-size: 13px;
  }

  button.delete {
    border-color: color-mix(in srgb, var(--wrong) 55%, transparent);
    background: transparent;
    color: var(--wrong);
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  input.file {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
  }

  .grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 14px 16px;
  }

  .wide {
    grid-column: 1 / -1;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  .field input,
  .field select,
  .field textarea,
  li.function input {
    width: 100%;
    box-sizing: border-box;
    height: 44px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: 10px;
    background: var(--paper);
    font-size: 15px;
  }

  .field input.name {
    font-size: 18px;
    font-weight: 650;
  }

  .field textarea {
    height: auto;
    min-height: 96px;
    padding: 10px 12px;
    line-height: 1.45;
    resize: vertical;
  }

  input:disabled {
    color: var(--hint);
    border-style: dashed;
    cursor: not-allowed;
  }

  input.length,
  input.addr,
  input.number {
    font-variant-numeric: tabular-nums;
  }

  .seg {
    display: flex;
    padding: 3px;
    border-radius: 11px;
    background: var(--rule);
  }

  .seg button {
    flex: 1;
    min-width: 0;
    height: 38px;
    padding: 0 8px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--hint);
    font-size: 13.5px;
    font-weight: 650;
    cursor: pointer;
  }

  .seg button[aria-pressed="true"] {
    background: var(--body);
    color: var(--ink);
  }

  .seg.mode button {
    height: 32px;
    font-size: 12.5px;
  }

  .sec {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-top: 18px;
    border-top: 1px solid var(--rule);
  }

  .sec h3 {
    color: var(--ink);
    font-size: 16px;
    letter-spacing: 0;
    text-transform: none;
  }

  .sec-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  button.switch {
    position: relative;
    flex: none;
    width: 50px;
    height: 30px;
    padding: 0;
    border: 0;
    border-radius: 999px;
    background: var(--rule);
    cursor: pointer;
  }

  button.switch i {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--body);
    transition: transform 120ms;
  }

  button.switch[aria-checked="true"] {
    background: var(--chosen);
  }

  button.switch[aria-checked="true"] i {
    transform: translateX(20px);
  }

  @media (prefers-reduced-motion: reduce) {
    button.switch i {
      transition: none;
    }
  }

  ul,
  ol {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  ul.functions {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  li.function {
    display: grid;
    grid-template-columns: 74px minmax(0, 1fr) minmax(170px, 210px) 36px;
    align-items: center;
    gap: 8px;
  }

  span.number {
    position: relative;
  }

  span.number input {
    padding-left: 24px;
    font-family: ui-monospace, monospace;
  }

  span.number i {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 10px;
    display: grid;
    place-items: center;
    color: var(--hint);
    font: 600 14px ui-monospace, monospace;
    pointer-events: none;
  }

  li.function button.remove {
    width: 36px;
    height: 36px;
    padding: 0;
    border: 0;
    border-radius: 9px;
    background: transparent;
    color: var(--hint);
    cursor: pointer;
  }

  ul.uses {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 14px;
  }

  .hint {
    margin: 0;
    color: var(--hint);
    font-size: 12.5px;
    line-height: 1.4;
  }

  /* Why a control is dead, said where the control is. */
  .why {
    color: var(--hint);
    font-size: 12px;
  }

  /* What the store refused, or what this refused before the store had to. */
  .trouble {
    margin: 0;
    color: var(--wrong);
    font-size: 13px;
    font-weight: 600;
  }

  /* --- the car's and the train's controls, until #979 and #980 --- */

  ul.rows > li + li {
    border-top: 1px solid var(--rule);
  }

  li.car {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 5rem 8rem 5rem auto;
    column-gap: 0.4rem;
    align-items: center;
    padding: 0.25rem 0;
  }

  li.entry {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 5rem 8rem auto auto;
    column-gap: 0.4rem;
    align-items: center;
    padding: 0.2rem 0;
  }

  li.addable {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    padding: 0.25rem 0;
  }

  li.car input,
  li.entry input,
  li.train input {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
    padding: 0.2rem 0.3rem;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--paper);
  }

  li.car > button,
  li.entry > button,
  li.train button,
  li.addable button {
    padding: 0.1rem 0.45rem;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--paper);
    cursor: pointer;
  }

  button.turn[aria-pressed="true"] {
    background: var(--rule);
  }

  li.car .why {
    grid-column: 1 / -1;
  }

  li.train > header {
    display: grid;
    grid-template-columns: 1fr auto auto;
    column-gap: 0.4rem;
    align-items: center;
  }

  li.train ol {
    margin-top: 0.4rem;
  }

  .derived {
    grid-column: 1 / -1;
    color: var(--hint);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .what {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  /* An item with nothing of its own: named by its model where it is used, and
     drawn as the product rather than as a thing with a name. */
  .what.anonymous {
    color: var(--hint);
    font-style: italic;
  }

  .of {
    color: var(--hint);
    font-size: 12px;
  }
`;
