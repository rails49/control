import { css } from "lit";

/**
 * The fast clock on the band (`tc-band-clock`): a round face about 40 px
 * across, the speed-up beside it in the band's ink where it is not 1, the
 * whole one press. In the dialog the day stands beside the time, and the
 * speed-up under both.
 */
export const bandClockStyles = css`
  :host {
    display: inline-flex;
    align-items: center;
  }

  button.face {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0;
    border: none;
    background: none;
    color: var(--band-ink, #fff);
    font: inherit;
    cursor: pointer;
  }

  tc-clock {
    width: 40px;
    height: 40px;
  }

  .faster {
    font-variant-numeric: tabular-nums;
  }

  .fields {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .when {
    display: flex;
    gap: 0.75rem;
  }

  .when .day {
    width: 5rem;
  }

  .when .time {
    flex: 1;
  }
`;
