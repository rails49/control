import { css } from "lit";

/**
 * The throttle view (`tc-throttle`): the trains to drive in the left pane, and
 * the one that is picked beside it (ui/THROTTLE.md).
 *
 * The pane is the shell's left-pane slot, whose width is the shell's
 * (`--pane`) — the same rectangle the editor's palette and the run view's
 * roster occupy, so switching view does not move the pane under the pointer
 * ([#169](https://github.com/rails49/control/issues/169)).
 *
 * The cab is one column: what the train is and the control that takes it, the
 * lever, the road in front, and the functions. The lever is the widest thing
 * on the page on purpose — it is what a hand reaches for, and STOP sits at the
 * end of it because centring is the press that matters
 * ([#207](https://github.com/rails49/control/issues/207)).
 */
export const throttleStyles = css`
  :host {
    display: grid;
    grid-template-columns: var(--pane) 1fr;
    overflow: hidden;
  }

  nav.trains {
    padding: 0.4rem;
    border-right: 1px solid var(--rule);
    overflow-y: auto;
  }

  h2 {
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
    margin: 0.3rem 0.2rem;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li + li {
    border-top: 1px solid var(--rule);
  }

  /* One train to pick: the name and the mark on one line, where it stands
     under them, as the roster pane's rows read. */
  button.train {
    display: grid;
    grid-template-columns: 1fr auto;
    column-gap: 0.5rem;
    align-items: baseline;
    width: 100%;
    padding: 0.25rem 0.2rem;
    border: none;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  button.train.picked {
    background: var(--rule);
  }

  .name {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  /* A train a person is holding, whoever they are: another tab counts. */
  .taken {
    font-size: 0.65rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--chosen);
  }

  .where {
    grid-column: 1 / -1;
    font-size: 0.7rem;
    color: var(--hint);
  }

  main {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    padding: 0.8rem 1rem;
    overflow-y: auto;
  }

  main h2 {
    margin: 0;
    font-size: 1rem;
    letter-spacing: 0;
    text-transform: none;
    color: var(--ink);
  }

  header {
    display: flex;
    gap: 0.6rem;
    align-items: baseline;
  }

  /* Which way the train points, which is what the lever's + means. */
  .facing {
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  .facing .arrow {
    color: var(--ink);
  }

  header button.take {
    margin-left: auto;
    padding: 0.25rem 0.9rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  header button.take.release {
    border-color: var(--chosen);
    color: var(--chosen);
  }

  button:disabled {
    color: var(--hint);
    cursor: default;
  }

  /* Why nothing can be driven: the power, or a session that is not there. */
  .still {
    margin: 0;
    padding: 0.3rem 0.5rem;
    border-left: 3px solid var(--wrong);
    background: var(--wrong-body);
  }

  .lever {
    display: flex;
    gap: 0.6rem;
    align-items: center;
  }

  input.speed {
    flex: 1;
    min-width: 0;
  }

  .reading {
    width: 3rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  /* The press that centres the lever, weighted like the thing a hand goes
     for without looking. */
  button.stop {
    padding: 0.3rem 1rem;
    border: 1px solid var(--wrong);
    border-radius: 4px;
    background: var(--body);
    color: var(--wrong);
    font: inherit;
    letter-spacing: 0.06em;
    cursor: pointer;
  }

  button.turn {
    padding: 0.3rem 0.8rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  /* What the train is reading, and the road in front of it. */
  .road {
    display: flex;
    gap: 0.6rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .aspect {
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    color: var(--body);
  }

  .aspect.stop {
    background: var(--red);
  }

  .aspect.caution {
    background: var(--amber);
  }

  .aspect.clear {
    background: var(--green);
  }

  ol.ahead {
    display: flex;
    gap: 0.3rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* The two colours a route is lit in on the run view, in a row: green where
     the dispatcher holds the lock and the train may move, cyan where the
     claim has not been made yet (ui/PANEL.md). */
  ol.ahead li {
    padding: 0.1rem 0.5rem;
    border: 1px solid var(--committed);
    border-radius: 3px;
    color: var(--committed);
  }

  ol.ahead li.locked {
    border-color: var(--locked);
    color: var(--locked);
  }

  .functions {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
  }

  button.function {
    padding: 0.25rem 0.7rem;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--body);
    font: inherit;
  }

  .hint {
    margin: 0;
    font-size: 0.7rem;
    line-height: 1.6;
    color: var(--hint);
  }
`;
