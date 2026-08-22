import { css } from "lit";

import { NOTE, W } from "../render/units.js";
import { page, symbols, way } from "./shared.styles.js";

/** The dispatch panel (`tc-panel`): trace replay painted over the drawing. */
export const panelStyles = css`
  :host {
    ${page}
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

  /* A committed route in two colours (ui/PANEL.md): green where the
     dispatcher holds the lock and the train may move, cyan where the route is
     chosen and the claim has not been made yet. The state rides on the
     symbol's group and on the wire, and the rules descend from there onto the
     lit classes that already exist, so what is lit stays one answer with one
     shape.

     Block state, strongest first: a train standing there, a lock holding the
     empty block ahead of it, a committed route not yet locked this far. A
     block is on no transit's way, so it takes its state from the block view
     and a junction symbol takes its from the route; occupancy outranks both.

     The pale ground a block body wears is mixed from its own stroke rather
     than named a second time, so one value moves a colour and its wash
     together and they cannot disagree. */
  .symbol.occupied .block-body {
    fill: #f6d3cb;
    stroke: var(--wrong);
  }

  .symbol.locked .block-body {
    fill: color-mix(in srgb, var(--locked) 18%, white);
    stroke: var(--locked);
  }

  /* Dashed against solid: cyan beside green is a hard pair for red-green
     deficiency, and whether the train may move is the distinction worth a
     channel that is not hue. Track and wires stay solid — a dash's spacing
     would vary with a wire's angle, which is why track is never patterned. */
  .symbol.planned .block-body {
    fill: color-mix(in srgb, var(--planned) 18%, white);
    stroke: var(--planned);
    stroke-dasharray: ${2 * W} ${W};
  }

  /* A throat has no block body, so it is the part of the route left with hue
     alone — and the part where which way is locked matters most. Recorded
     rather than hidden (ui/PANEL.md). */
  .symbol.locked .track.lit,
  .symbol.locked .tick.lit,
  .wire.lit.locked {
    stroke: var(--locked);
  }

  .symbol.locked .bend.lit {
    fill: var(--locked);
  }

  .symbol.planned .track.lit,
  .symbol.planned .tick.lit,
  .wire.lit.planned {
    stroke: var(--planned);
  }

  .symbol.planned .bend.lit {
    fill: var(--planned);
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

  /* A train between two blocks, on the connection it is crossing (#154). The
     label sits over the throat rather than over a block, so it carries the
     sheet behind its own strokes to stay readable. */
  .name.train.crossing {
    paint-order: stroke;
    stroke: var(--paper);
    stroke-width: ${2 * W};
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
