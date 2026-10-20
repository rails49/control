import { css } from "lit";

/**
 * The train picker (`tc-train-picker`): a grid of cards, two across on a
 * phone's 390 px and more as the window widens, with the Take back card
 * apart above it (ui/THROTTLE.md). Every press is at least 44 px high, a
 * thumb's target.
 *
 * `compact`, in the throttle view's take column, each card is a row: a small
 * thumbnail, then the name and where, then its press.
 */
export const pickerStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    padding: 0.8rem 1rem;
    overflow-y: auto;
    min-height: 0;
  }

  h2 {
    margin: 0;
    font-size: 1rem;
    color: var(--ink);
  }

  ul.cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
    gap: 0.6rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.4rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
  }

  /* The last train held, apart from the grid. */
  .card.back {
    max-width: 20rem;
    border-color: var(--chosen);
  }

  /* Another throttle holds it: everything but the Force release, which is
     still a press to make. */
  .card.faded > :not(button) {
    opacity: 0.5;
  }

  .thumbnail {
    display: block;
    width: 100%;
    aspect-ratio: 3 / 2;
    object-fit: contain;
  }

  /* No photo: the name stands in its place. */
  .thumbnail.name {
    display: grid;
    place-items: center;
    color: var(--hint);
  }

  .mine {
    font-size: 0.65rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--chosen);
  }

  .name {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .where,
  .holder {
    font-size: 0.7rem;
    color: var(--hint);
  }

  button {
    min-height: 44px;
    margin-top: auto;
    padding: 0.25rem 0.9rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  button.back,
  button.force {
    border-color: var(--chosen);
    color: var(--chosen);
  }

  button:disabled {
    color: var(--hint);
    cursor: default;
  }

  /* Why nothing can be taken: the power, or a session that is not there. */
  .still {
    margin: 0;
    padding: 0.3rem 0.5rem;
    border-left: 3px solid var(--wrong);
    background: var(--wrong-body);
  }

  :host([compact]) {
    padding: 0;
  }

  :host([compact]) ul.cards {
    grid-template-columns: 1fr;
  }

  :host([compact]) .card {
    display: grid;
    grid-template-columns: 4.5rem 1fr auto;
    grid-template-rows: auto auto auto;
    column-gap: 0.5rem;
    align-items: center;
    max-width: none;
  }

  :host([compact]) .thumbnail {
    grid-row: 1 / -1;
  }

  :host([compact]) .card > :not(.thumbnail, button) {
    grid-column: 2;
  }

  :host([compact]) button {
    grid-column: 3;
    grid-row: 1 / -1;
    margin-top: 0;
  }

  .hint {
    margin: 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
