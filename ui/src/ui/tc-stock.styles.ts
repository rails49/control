import { css } from "lit";

/**
 * The stock view (`tc-stock`): what can go in a train on the left, the trains
 * on the right (ui/STOCK.md).
 *
 * **Not the shell's left-pane slot.** `--pane` is the width of the strip
 * beside a drawing surface — the editor's palette, the run view's roster
 * ([#169](https://github.com/rails49/control/issues/169)) — and this view has
 * no surface: it is two columns of documents, and the left one carries three
 * fields per row rather than a tile. So it declares its own width and leaves
 * `--pane` to the three views that share the rectangle.
 *
 * **Cars above, models below.** Cars are yours and are few; models are what
 * anything is made of, and ten identical hoppers are one row rather than ten
 * ([ADR-0061](../../../docs/adr/0061-stock-with-nothing-of-its-own-is-named-by-its-model.md)).
 * Each list scrolls on its own, so a long catalogue does not push the cars off
 * the top of the screen.
 *
 * A row is a grid rather than a flex line, so the addresses and the lengths
 * read down their columns; both are numbers and both are tabular. A control
 * the length guard has killed keeps its box and takes the hint colour, with
 * the reason beside it — a field that vanished while a train was placed would
 * leave a person looking for it (ui/STOCK.md#the-length-guard).
 *
 * **A thumbnail starts every row**, a fixed column wide enough to tell two
 * products apart and small enough that the fields keep the width they had: a
 * photo answers *which one is that* faster than a name does, and the picture
 * itself is a dialog away (ui/STOCK.md#a-models-photo).
 */
export const stockStyles = css`
  :host {
    display: grid;
    grid-template-columns: minmax(20rem, 28rem) 1fr;
    overflow: hidden;
  }

  section.parts {
    display: grid;
    grid-template-rows: 1fr 1fr;
    border-right: 1px solid var(--rule);
    overflow: hidden;
  }

  section.cars,
  section.models,
  section.trains {
    display: flex;
    flex-direction: column;
    padding: 0.4rem;
    overflow: hidden;
  }

  section.cars {
    border-bottom: 1px solid var(--rule);
  }

  header.head {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin: 0.3rem 0.2rem;
  }

  h2 {
    flex: 1;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
    margin: 0;
  }

  ul,
  ol {
    flex: 1;
    margin: 0;
    padding: 0;
    list-style: none;
    overflow-y: auto;
  }

  li + li {
    border-top: 1px solid var(--rule);
  }

  /* One car and one model read as the same row: the photo, what it is, then
     the numbers, then the two presses. The thumbnail is the first column on
     both because a car's photo is its model's, so the two lists read down one
     edge (ADR-0061). */
  li.car,
  li.product {
    display: grid;
    grid-template-columns: 3.2rem 1fr 5rem 5rem auto auto;
    column-gap: 0.4rem;
    align-items: center;
    padding: 0.25rem 0.2rem;
  }

  li.entry {
    display: grid;
    grid-template-columns: 1fr 5rem auto auto;
    column-gap: 0.4rem;
    align-items: center;
    padding: 0.2rem 0.2rem;
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
    font-size: 0.7rem;
    color: var(--hint);
  }

  input,
  select {
    width: 100%;
    min-width: 0;
    padding: 0.15rem 0.25rem;
    border: 1px solid var(--rule);
    border-radius: 3px;
    background: var(--paper);
    color: var(--ink);
    font: inherit;
  }

  input.addr,
  input.length {
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  input:disabled {
    color: var(--hint);
    cursor: not-allowed;
  }

  /* Why a control is dead, said where the control is. */
  .why {
    grid-column: 1 / -1;
    font-size: 0.7rem;
    color: var(--hint);
  }

  button {
    padding: 0.1rem 0.35rem;
    border: 1px solid var(--rule);
    border-radius: 3px;
    background: var(--paper);
    color: var(--ink);
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    color: var(--hint);
    cursor: not-allowed;
  }

  button.turn[aria-pressed="true"] {
    background: var(--rule);
  }

  li.train {
    padding: 0.35rem 0.2rem;
  }

  /* The train a press on the left is about. One is current at a time, the way
     one palette tile is armed at a time. */
  li.train.current {
    background: var(--rule);
  }

  li.train > header {
    display: grid;
    grid-template-columns: 1fr auto auto;
    column-gap: 0.4rem;
    align-items: center;
  }

  .derived {
    grid-column: 1 / -1;
    font-size: 0.7rem;
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  .hint {
    margin: 0.6rem 0.2rem 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }

  /* What the store refused, or what this refused before the store had to. */
  .trouble {
    margin: 0.3rem 0.2rem;
    font-size: 0.75rem;
    color: var(--wrong);
  }

  sl-dialog .field {
    display: block;
    margin-bottom: 0.6rem;
  }

  sl-dialog label {
    display: block;
    font-size: 0.75rem;
    color: var(--hint);
  }

  li.function {
    display: grid;
    grid-template-columns: 4rem 1fr auto;
    column-gap: 0.4rem;
    align-items: center;
    padding: 0.15rem 0;
  }

  /* A model's photo. The thumbnail is a press, so it is a button and not an
     image with a handler on it: what it opens is a dialog, and the keyboard
     reaches it the way it reaches the + beside it. */
  button.thumb {
    width: 3.2rem;
    height: 1.9rem;
    padding: 0;
    overflow: hidden;
    font-size: 0.55rem;
    line-height: 1;
    color: var(--hint);
  }

  button.thumb img,
  .picture img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  /* The frame the photo is shown in, at a fixed shape whether there is a
     picture in it, none, or a camera being waited on: a dialog whose height
     moved under the presses would move the press being aimed at. */
  .picture {
    aspect-ratio: 4 / 3;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--rule);
    border-radius: 3px;
    overflow: hidden;
    font-size: 0.8rem;
    color: var(--hint);
    text-align: center;
  }

  .picture.waiting {
    border-style: dashed;
  }

  /* A picture nothing has been told to keep, marked so it is not mistaken for
     the photo the model has. */
  .picture.unsaved {
    outline: 2px dashed var(--ink);
    outline-offset: 2px;
  }

  .presses {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.5rem;
  }

  .unkept {
    margin: 0.3rem 0 0;
    font-size: 0.75rem;
    color: var(--hint);
  }

  /* Why there is no picture, or what the store said about keeping one. Not
     the dialog's trouble line: that one is the New model dialog's own refusal,
     and a camera that answered something other than a picture is no refusal of
     the product being written (#446). */
  .no-picture {
    margin: 0.3rem 0 0;
    font-size: 0.75rem;
    color: var(--wrong);
  }
`;
