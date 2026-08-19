import { css } from "lit";

/** The netlist pane (`tc-netlist`). */
export const netlistStyles = css`
  :host {
    display: block;
    font: 13px/1.45 system-ui, sans-serif;
  }

  h2,
  h3 {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    margin: 0.9rem 0 0.3rem;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--hint);
  }

  h2 {
    color: var(--ink);
  }

  .count {
    font-weight: 400;
    color: var(--hint);
    text-transform: none;
    letter-spacing: 0;
  }

  /* The symbols a connection is drawn from, under its heading: a name nobody
     typed is read here, and so is a junction wider than it looks. */
  .drawn-from {
    margin: 0 0 0.35rem;
    font-size: 0.75rem;
    color: var(--hint);
    word-spacing: 0.2em;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* The symbol inspector sits above the netlist: it answers the question just
     asked on the canvas, and scrolling to find it would be the wrong way
     round. */
  section.symbol {
    margin-bottom: 0.9rem;
    padding: 0.1rem 0.5rem 0.5rem;
    border-left: 3px solid var(--tint-2);
    background: #faf5ee;
  }

  .concurrent {
    margin: 0.15rem 0 0.3rem 0.3rem;
    color: var(--tint-1);
  }

  .concurrent li::before {
    content: "runs with  ";
    color: var(--hint);
  }

  .blocks li {
    display: flex;
    justify-content: space-between;
    padding: 0.1rem 0.3rem;
  }

  .transits button {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    width: 100%;
    padding: 0.2rem 0.3rem;
    border: none;
    border-radius: 3px;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .transits button:hover {
    background: #f0eeea;
  }

  .transits button.on {
    background: #e8f0fe;
    font-weight: 600;
  }

  .ends,
  .why {
    color: var(--hint);
    font-variant-numeric: tabular-nums;
  }

  .against {
    margin: 0.2rem 0 0.5rem 0.8rem;
    border-left: 2px solid var(--rule);
  }

  .against li {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.1rem 0.4rem;
  }

  .against .with span:first-child {
    color: var(--tint-1);
  }

  .against .without span:first-child {
    color: var(--wrong);
  }

  .hint {
    color: var(--hint);
  }
`;
