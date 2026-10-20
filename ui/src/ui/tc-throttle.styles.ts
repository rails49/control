import { css } from "lit";

/**
 * The throttle view (`tc-throttle`): the train picker while this throttle
 * holds no train, whose styles are its own (`tc-train-picker.styles.ts`), and
 * the driving controls of each train it holds, whose styles are theirs
 * (`tc-driving.styles.ts`), laid out here (ui/THROTTLE.md,
 * [#855](https://github.com/rails49/control/issues/855)).
 *
 * Side by side, a train's column is at least 360 px, the take column 260 px
 * and the gap 14 px — the numbers `columns` (`model/throttle.ts`) counts
 * with, the count handed in as `--columns`. Stacked, on a phone, the trains'
 * controls stand one below the other in the same `.trains`: the two layouts
 * differ by class alone, so a width change keeps each train's controls. A
 * view too short for them scrolls.
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

  main.stacked .trains {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  main.stacked tc-driving + tc-driving {
    padding-top: 0.8rem;
    border-top: 1px solid var(--rule);
  }

  main.side {
    flex-direction: row;
    align-items: flex-start;
    gap: 14px;
  }

  main.side .trains {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(var(--columns), minmax(360px, 1fr));
    gap: 14px;
  }

  aside.take {
    flex: 0 0 260px;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 0.6rem;
  }

  aside.take h2 {
    margin: 0;
    font-size: 1rem;
    color: var(--ink);
  }

  aside.take tc-train-picker {
    padding: 0;
  }

  .hint {
    margin: 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
