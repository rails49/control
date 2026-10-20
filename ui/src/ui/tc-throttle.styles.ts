import { css } from "lit";

/**
 * The throttle view (`tc-throttle`): the train picker while this throttle
 * holds no train, whose styles are its own (`tc-train-picker.styles.ts`), and
 * the driving controls of each train it holds, whose styles are theirs
 * (`tc-driving.styles.ts`), laid out here (ui/THROTTLE.md).
 *
 * A window too short for the controls scrolls them.
 */
export const throttleStyles = css`
  :host {
    display: grid;
    overflow: hidden;
  }

  main {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    padding: 0.8rem 1rem;
    overflow-y: auto;
    min-height: 0;
  }
`;
