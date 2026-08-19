import { css } from "lit";

import { NOTE, W } from "../render/units.js";
import { palette, symbols, way } from "./shared.styles.js";

/** The dispatch panel (`tc-panel`): trace replay painted over the drawing. */
export const panelStyles = css`
  :host {
    ${palette}

    display: grid;
    grid-template-rows: auto auto 1fr;
    height: 100vh;
    background: var(--paper);
    color: var(--ink);
    font: 13px/1.4 system-ui, sans-serif;
  }

  header {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--rule);
  }

  header .spacer {
    flex: 1;
  }

  header label.rate {
    display: flex;
    gap: 0.4rem;
    align-items: center;
    color: var(--hint);
  }

  main {
    overflow: hidden;
  }

  svg {
    width: 100%;
    height: 100%;
    user-select: none;
  }

  .sheet {
    fill: var(--paper);
  }

  ${symbols}

  ${way}

  /* Block state, strongest first: a train standing there, a lock holding the
     empty block ahead of it, a committed route not yet locked this far. The
     reserved fill is the lit tint, so a committed route reads as one lit path
     whether a stretch is locked yet or merely chosen. */
  .symbol.occupied .block-body {
    fill: #f6d3cb;
    stroke: var(--wrong);
  }

  .symbol.reserved .block-body {
    fill: var(--lit-body);
    stroke: var(--lit);
  }

  .symbol.planned .block-body {
    fill: var(--lit-body);
    stroke: var(--lit);
    stroke-dasharray: ${2 * W} ${W};
  }

  /* Signal aspects. The artwork draws both lamps; run mode shows one: red as
     the resting aspect, green at an end whose resource beyond is locked to
     the train standing there (locked-ahead, ui/PANEL.md). */
  .signal .lamp {
    opacity: 0.18;
  }

  .signal .lamp.danger {
    opacity: 1;
  }

  .symbol.green-A .signal.end-A .lamp.danger,
  .symbol.green-B .signal.end-B .lamp.danger {
    opacity: 0.18;
  }

  .symbol.green-A .signal.end-A .lamp.clear,
  .symbol.green-B .signal.end-B .lamp.clear {
    opacity: 1;
  }

  /* A block's label: its train when one stands there, its own name dimly
     otherwise. Drawn outside the turned group and sized per label, as the
     editor does. */
  .name {
    font-family: system-ui, sans-serif;
    fill: var(--hint);
    text-anchor: middle;
    dominant-baseline: middle;
    pointer-events: none;
  }

  .name.train {
    fill: var(--ink);
    font-weight: 600;
  }

  /* The direction arrow: where the occupying train's nose points. */
  .arrow {
    fill: var(--ink);
  }

  /* Request endpoints (ui/PANEL.md): a pending request is endpoints only,
     never a predicted path. Departure end filled, candidate arrival ends
     open, pruned ends dimmed, a rejection in red with its reason in words. */
  .marker {
    fill: none;
    stroke: var(--chosen);
    stroke-width: ${0.6 * W};
  }

  .marker.depart {
    fill: var(--chosen);
  }

  .marker.pruned {
    stroke: var(--hint);
    stroke-dasharray: ${W} ${0.6 * W};
  }

  .marker.rejected {
    stroke: var(--wrong);
  }

  .note {
    font: ${NOTE}px system-ui, sans-serif;
    fill: var(--hint);
    text-anchor: middle;
  }

  .note.rejected {
    fill: var(--wrong);
  }

  /* Scheduling by drag (#72). A live session is the only one that can submit,
     so only there does a train look like something to pick up. */
  svg.scheduling .symbol.occupied {
    cursor: grab;
  }

  /* The gesture in flight: the reach from where the train was taken hold of,
     and a ring at each arrival end a drop here would ask for. Both are drawn
     from the drag model's answer, never from a guess about feasibility. */
  .reach {
    stroke: var(--chosen);
    stroke-width: ${W};
    stroke-dasharray: ${3 * W} ${2 * W};
    opacity: 0.7;
    pointer-events: none;
  }

  .marker.hover {
    fill: none;
    stroke: var(--chosen);
    stroke-width: ${0.9 * W};
    pointer-events: none;
  }

  .symbol.target .block-body {
    stroke: var(--chosen);
  }
`;
