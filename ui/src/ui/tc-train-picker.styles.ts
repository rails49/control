import { css } from "lit";

/**
 * The train selector (`tc-train-picker`): a header, a grid of cards two
 * across, and a full-width Release, filling a throttle's panel — over the
 * driving controls where it was opened from the picture (ui/THROTTLE.md).
 * Every press is at least 40 px high, a thumb's target; the dialog that asks
 * before taking a train another throttle holds sits over the selector.
 */
export const pickerStyles = css`
  :host {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    min-height: 0;
    background: var(--paper);
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.8rem;
  }

  h2 {
    margin: 0;
    font-size: 1.1rem;
    color: var(--ink);
  }

  .sub {
    margin: 0.1rem 0 0;
    font-size: 0.75rem;
    color: var(--hint);
  }

  button {
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  /* Dead: no train to release, or rails a train may not move on. */
  button:disabled,
  button[aria-disabled="true"] {
    cursor: default;
  }

  .card[aria-disabled="true"],
  button.confirmed[aria-disabled="true"] {
    filter: grayscale(1);
  }

  button.close {
    flex: none;
    width: 40px;
    height: 40px;
    padding: 0;
    border-radius: 50%;
  }

  ul.cards {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: grid;
    grid-template-columns: 1fr 1fr;
    align-content: start;
    gap: 0.6rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    width: 100%;
    padding: 0 0 0.5rem;
    overflow: hidden;
    text-align: left;
  }

  .card > span:not(.thumbnail) {
    padding: 0 0.5rem;
  }

  /* The panel's own train. */
  .card.mine {
    border-color: var(--chosen);
    box-shadow: 0 0 0 1.5px var(--chosen);
  }

  .card.mine .holder {
    color: var(--chosen);
    font-weight: 600;
  }

  /* Another throttle holds it: still a press, which asks first. */
  .card.faded {
    opacity: 0.45;
  }

  .thumbnail {
    display: block;
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: contain;
  }

  /* No photo: the name stands in its place. */
  .thumbnail.stand-in {
    display: grid;
    place-items: center;
    color: var(--hint);
  }

  .name {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-weight: 600;
  }

  .where,
  .holder {
    font-size: 0.7rem;
    color: var(--hint);
  }

  footer {
    padding-top: 0.6rem;
    border-top: 1px solid var(--rule);
  }

  button.release {
    width: 100%;
    height: 48px;
    border-color: var(--chosen);
    color: var(--chosen);
  }

  button.release:disabled,
  button.release[aria-disabled="true"] {
    border-color: var(--rule);
    color: var(--hint);
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

  /* Taking a train another throttle holds: asked inside the panel. */
  .confirm {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 1.2rem;
    background: color-mix(in srgb, var(--ink) 35%, transparent);
  }

  .dialog {
    max-width: 20rem;
    padding: 1.2rem;
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--body);
  }

  .dialog h3 {
    margin: 0 0 0.5rem;
  }

  .dialog p {
    margin: 0 0 1rem;
    line-height: 1.45;
    color: var(--hint);
  }

  .row {
    display: flex;
    gap: 0.6rem;
  }

  .row button {
    flex: 1;
    height: 46px;
  }

  button.confirmed {
    border-color: var(--chosen);
    background: var(--chosen);
    color: var(--body);
  }
`;
