import { css } from "lit";

/**
 * The train picker (`tc-train-picker`): a grid of cards filling a
 * throttle's panel, two across on a phone's 390 px (ui/THROTTLE.md). Every
 * press is at least 44 px high, a thumb's target.
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

  .hint {
    margin: 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
