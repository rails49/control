import { css } from "lit";

/**
 * The throttle view (`tc-throttle`): a row of throttles, each a panel the
 * size of a phone screen holding the train picker, whose styles are its own
 * (`tc-train-picker.styles.ts`), or one train's driving controls, whose styles
 * are theirs (`tc-driving.styles.ts`), laid out here (ui/THROTTLE.md,
 * ADR-0089).
 *
 * Each panel's width and height are set on it, from `panels` and
 * `panelHeight` (`model/throttle.ts`), and the number across is handed in as
 * `--count`. Side by side, the row has the 8 px margin and the 20 px gap
 * `panels` counts with, and is centred; `single`, on a phone, the panel is the
 * view's whole width with neither. Panels are top-aligned, those beyond the
 * count wrap onto a further row, and a view too short for them scrolls.
 */
export const throttleStyles = css`
  :host {
    display: grid;
    overflow: hidden;
  }

  main {
    display: grid;
    grid-template-columns: repeat(var(--count), auto);
    align-content: start;
    align-items: start;
    justify-content: center;
    overflow: auto;
    min-height: 0;
  }

  main.row {
    padding: 8px;
    gap: 20px;
  }

  main.single {
    grid-template-columns: 100%;
  }

  .panel {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    padding: 0.8rem 1rem;
    overflow-y: auto;
  }

  main.row .panel {
    border: 1px solid var(--rule);
    border-radius: 4px;
  }

  main.single .panel + .panel {
    border-top: 1px solid var(--rule);
  }

  .panel > tc-train-picker {
    padding: 0;
  }
`;
