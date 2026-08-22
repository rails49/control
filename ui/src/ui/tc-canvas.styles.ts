import { css } from "lit";

import { NOTE, RING, SLIP, W } from "../render/units.js";
import { palette, symbols } from "./shared.styles.js";

/**
 * What the drawing surface wears whichever mode it is in: the sheet, the
 * symbols, the wires and a way lit over them.
 *
 * There is one surface that paints a whole drawing (ADR-0038), so what used to
 * be shared between the editor's canvas and the panel is simply the canvas's
 * own. The two modes' rules are declared apart below, so that neither mode's
 * marks can bleed into the other by a selector that happens to match — and so
 * that an exported file carries the edit mode's rules alone.
 */
const sheet = css`
  :host {
    display: block;
    overflow: hidden;
  }

  svg {
    width: 100%;
    height: 100%;
    touch-action: none;
    user-select: none;
  }

  .sheet {
    fill: var(--paper);
  }

  ${symbols}

  /* A wire is track: same width, same round cap, so it joins a symbol's leg
     seamlessly at whatever angle its two pins give it. */
  .wire {
    stroke: var(--track);
    stroke-width: ${W};
    stroke-linecap: round;
  }

  /* The generic connection symbol shows no turnout detail, which is what it
     says about itself. */
  .opaque {
    fill: #edeae4;
    stroke: var(--track);
    stroke-width: ${0.5 * W};
    stroke-dasharray: ${2 * W} ${W};
  }

  /* A lit way, leg by leg: the legs of the symbols on it. In edit mode it is
     the transit chosen in the netlist pane; in run mode it is a committed
     route — the same claim, made by the dispatcher instead of the pointer. */
  .symbol .track.lit {
    stroke: var(--lit);
    stroke-width: ${1.6 * W};
  }

  /* The wires between those legs, at the same weight, so a way reads as one
     continuous run rather than as scattered lit frogs — and so a way across a
     joint, which crosses no symbol declaring a transit, lights at all. Which
     wires those are is model/inspect.ts, per way. */
  .wire.lit {
    stroke: var(--lit);
    stroke-width: ${1.6 * W};
  }

  .symbol .bend.lit {
    fill: var(--lit);
  }

  /* A slip's tick is the only thing telling its road from the through route, so
     it lights with the transit. It stays a mark: half again its own weight is
     enough to read beside track three times as thick. */
  .symbol .tick.lit {
    stroke: var(--lit);
    stroke-width: ${SLIP.lit};
  }

  /* A block's body covers all but the stubs of its track, so the end of a lit
     transit would otherwise be two orange flecks. */
  .symbol .block-body.lit,
  .symbol .opaque.lit {
    fill: var(--lit-body);
    stroke: var(--lit);
  }

  /* A block's label, the only text on a symbol: centred in its rectangle rather
     than sitting on a point. The size is set per label rather than here, being
     the size that name fits the rectangle at (render/units.ts). */
  .name {
    font-family: system-ui, sans-serif;
    fill: var(--ink);
    text-anchor: middle;
    dominant-baseline: middle;
    pointer-events: none;
  }
`;

/** What only the editing surface wears: the marks that answer a question about
 *  the drawing, and the parts of a gesture in flight. */
const editing = css`
  .faces {
    pointer-events: none;
  }

  /* A face centre. Ruled lines would have marked the cell corners, which are
     the one class of point a wire can never land on. */
  .face {
    fill: var(--face);
  }

  /* A square two symbols both cover, marked over the artwork so the overlap a
     rotate or a flip made is visible where it is. In the quieter weight: an
     overlap is cosmetic and the drawing derives regardless, so marking it in
     the red a pin short of a wire wears would overstate it (ADR-0024). Heavier
     than the red mark to make up for the slate, which reads fainter over paper
     at the same opacity. */
  .stacked {
    fill: var(--unfinished);
    opacity: 0.3;
    pointer-events: none;
  }

  /* A turnout or a slip carrying no address, ringed on the squares it covers.
     The drawing derives without one and cannot be driven, which is what the
     quieter of the two weights says (ADR-0024); it is the same slate an
     overlap wears, since there are two weights and not three.

     A ring rather than a wash: a tinted square is already what an overlap
     looks like, and a wash over the symbol would hide the very artwork the
     mark is about. Drawn under the pins the way the artwork is. */
  .unaddressed {
    fill: none;
    stroke: var(--unfinished);
    stroke-width: ${RING.weight};
    stroke-dasharray: ${RING.dash} ${RING.gap};
    pointer-events: none;
  }

  /* The wire following the pointer is an affordance rather than track, so it
     keeps its width as the canvas is zoomed. */
  .wireline {
    stroke: var(--chosen);
    stroke-width: 2;
    stroke-dasharray: 6 4;
    vector-effect: non-scaling-stroke;
    pointer-events: none;
  }

  .symbol.selected .track,
  .symbol.selected .wire {
    stroke: var(--chosen);
  }

  .symbol.selected .block-body,
  .symbol.selected .opaque {
    stroke: var(--chosen);
  }

  /* The way a refusal is about, lit in the red that means derivation stopped
     rather than in the colour a chosen transit wears (ADR-0024). It reads as
     one run for the same reason a chosen transit does — every leg of it and
     both its block ends — and the rules ride on the lit classes so that what
     is lit stays one answer with one shape. The selection rules come first: a
     symbol both selected and on the way shows the way, which is the answer to
     the question selecting it asked. */
  .symbol.offending .track.lit {
    stroke: var(--wrong);
  }

  .symbol.offending .tick.lit {
    stroke: var(--wrong);
  }

  .symbol.offending .bend.lit {
    fill: var(--wrong);
  }

  .symbol.offending .block-body.lit,
  .symbol.offending .opaque.lit {
    fill: var(--wrong-body);
    stroke: var(--wrong);
  }

  /* A wire is not inside a symbol's group, so it carries the mark itself
     rather than inheriting it from one. Same rule, same red: a refusal about
     a route points at the whole route, wires included. */
  .wire.lit.offending {
    stroke: var(--wrong);
  }

  /* The label a portal pairing with nothing wears, beside its mouth: the only
     text a symbol other than a block carries, and there only while the drawing
     is wrong, so colour on the canvas still means trouble
     (EDITOR.md#symbol-geometry).

     It is not a name rule, though it is drawn like one: a name is what a symbol
     carries and this is a fault mark, and which end of it sits on the point is
     the mark's own direction speaking, through the attribute a rule here would
     beat. */
  .unpaired {
    font-family: system-ui, sans-serif;
    fill: var(--wrong);
    dominant-baseline: middle;
    pointer-events: none;
  }

  /* Every pin is drawn while editing, green where it has the wire it wants and
     red where it does not. The verdict is the store's, not the canvas's. */
  .pin {
    fill: var(--good);
  }

  .pin.red {
    fill: var(--wrong);
  }

  .pin.pending {
    fill: var(--chosen);
  }

  /* The symbol on its way out of the palette, drawn where a drop would put it.
     Faint, so what is already on the sheet reads through it and the ghost is
     plainly not placed yet; the squares it cannot have are marked where they
     are, as an overlap is. */
  .ghost {
    opacity: 0.45;
    pointer-events: none;
  }

  .ghost.blocked {
    opacity: 0.3;
  }

  /* Under the ghost the same square is a refusal rather than an overlap: the
     drop places nothing (EDITOR.md#canvas), and what stops something is red.
     The rule sits on the ancestor rather than on a class of its own, so the
     mark cannot be renamed on one side and left on the other. */
  .ghost.blocked .stacked {
    fill: var(--wrong);
    opacity: 0.22;
  }

  .band {
    fill: var(--chosen);
    fill-opacity: 0.08;
    stroke: var(--chosen);
    stroke-width: 1;
    stroke-dasharray: 4 3;
    vector-effect: non-scaling-stroke;
  }
`;

/** What only the running surface wears: a live session painted over the
 *  drawing (ui/PANEL.md). */
const running = css`
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
     drawn faint, so a turnout on a run shows which way it is set and the
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

  /* A block showing its own name rather than a train's: the name is what is
     left when there is nothing to read, so it stands back. */
  .name.dim {
    fill: var(--hint);
  }

  .name.train {
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

  /* What the detectors dispute (#153). The outline rides over whatever state
     the block is in rather than replacing its colour: the dispute is that the
     block is other than the picture says, and the picture is the half a
     person is checking. Amber, not the red a rejection wears — nothing is
     broken, and the railroad is as likely to be right as the software. It is
     the last stroke declared for a block body, so it wins on specificity ties
     without a rule of its own for each state. */
  .symbol.disputed .block-body {
    stroke: var(--amber);
    stroke-width: ${2 * W};
  }

  .note.disputed {
    fill: var(--amber);
  }

  /* Scheduling by drag (#72). Only a joined session can submit, so only when
     the view says so does a train look like something to pick up. */
  :host(.scheduling) .symbol.occupied {
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

/** The drawing surface (`tc-canvas`), both modes. Which one is drawing decides
 *  which marks are on the sheet, so the rules can all be declared: run mode
 *  emits no `.pin` and edit mode emits no `.occupied`. */
export const canvasStyles = css`
  ${sheet}
  ${editing}
  ${running}
`;

/**
 * What an exported file carries: the rules the drawing on it was painted with,
 * and the palette they read (#86).
 *
 * On screen the custom properties come off `tc-app`'s host and the canvas
 * inherits them; a file has no host above it, so they are written onto the svg
 * itself. Both sides read the same `COLOURS`, and the rules are the very
 * blocks the canvas renders with rather than a copy of them, so the file
 * cannot drift from the screen. An export is of the edit mode's sheet, so a
 * run's rules are no part of it.
 */
export const exportStyles = css`
  svg {
    ${palette}
  }

  ${sheet}
  ${editing}
`;
