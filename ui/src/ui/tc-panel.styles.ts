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

  /* Where a point lies (CONTEXT.md): the road its position does not offer is
     drawn faint, so a turnout on the panel shows which way it is set and the
     editor's plain drawing keeps saying only what a point is. Fading rather
     than recolouring, because this is not a fault and not a way lit: the road
     is simply not on offer. A lit leg the points are not yet set for fades
     with it, which is the honest picture — the route is chosen and the
     alignment has not happened yet. */
  .symbol .track.against,
  .symbol .tick.against {
    opacity: 0.25;
  }

  /* Signal aspects, as the Swiss standard sets them: stop is red alone,
     approach is green with amber, clear is green alone. The artwork draws
     every lamp and the aspect lights a set of them, so the aspect is a class
     on the signal's group and never on a lamp (ui/PANEL.md). Every end rests
     at stop, which is what an end no train may leave by keeps showing. */
  .signal .lamp {
    opacity: 0.18;
  }

  .signal.stop .lamp.red,
  .signal.approach .lamp.green,
  .signal.approach .lamp.amber,
  .signal.clear .lamp.green {
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
