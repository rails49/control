/**
 * What a drag on the live panel means: take hold of a train, drop it on a
 * block, get the arrival ends the drop asks for (ui/PANEL.md, #72).
 *
 * Grid coordinates in, an arrival-end set or a cancel out. No DOM: the canvas
 * converts the pointer's pixels into squares and calls one method per event,
 * exactly as the editor's `Gesture` is called, so every rule after the
 * conversion is testable without a browser.
 *
 * The gesture is **filter-free**. It never asks whether a train fits, whether
 * an end is enterable, or whether a route exists — every drop submits and the
 * dispatcher answers. The one refusal here is the train's own block, which is
 * the cancel gesture and not a judgement about feasibility — or either of the
 * two its name is in while it passes from one to the next — and, for a train
 * crossing a transit, every block, since it has none of its own to be moved
 * from and only the drop on the roster pane means anything (ADR-0069).
 *
 * The departure end is no part of this, and neither is a request id: a drop
 * is a gesture, and both are what the scheduler adds when it composes the
 * request the gesture asks for
 * ([ADR-0036](../../../docs/adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)).
 */

import type { Drawing } from "./drawing.js";
import { anchorOf, type Point } from "./geometry.js";
import type { Machine, Outcome } from "./machine.js";
import type { BlockView, EndRef } from "./panel.js";
import type { Review } from "./store.js";
import type { PointWanted } from "./trace.js";
import { nearest, pressableAt, under } from "./under.js";

/** How far the pointer may travel, in screen pixels, between the press on a
 *  point and the release that throws it: a click, and a shaky hand is still
 *  one. The editor allows the same before a press on a pin is a drag. */
const SLOP = 4;

/** The same for a finger, which rolls as it lifts (#893). */
const TOUCH_SLOP = 12;

/** How far from a tap, in squares, the offered point it throws may be: a
 *  fingertip covers about a square at the zoom a panel is read at (#893). */
const TOUCH_REACH = 1;

/** What a drop asks for: one block, and the ends the train may enter through
 *  — one for an outer third, both for the middle. */
export interface Drop {
  train: string;
  block: string;
  dest: EndRef[];
}

interface Held {
  train: string;
  /** The blocks the train's name is in, a drop on which cancels, or `null`
   *  for a train crossing a transit: it has no block of its own, so no drop
   *  on a block means anything for it (ADR-0069). */
  own: readonly string[] | null;
  from: Point;
  to: Point;
}

export class Drag {
  private held: Held | null = null;
  private proposal: Drop | null = null;

  /** The train being dragged, where one is. */
  get train(): string | null {
    return this.held?.train ?? null;
  }

  /** Where the drag began and where the pointer is, for the line the canvas
   *  draws between them. */
  get from(): Point | null {
    return this.held?.from ?? null;
  }

  get to(): Point | null {
    return this.held?.to ?? null;
  }

  /** What a drop where the pointer is would ask for — what the canvas
   *  highlights so the operator can see it before releasing. */
  get drop(): Drop | null {
    return this.proposal;
  }

  /** A press: it takes hold only on a block carrying a train's name. */
  down(
    drawing: Drawing,
    review: Review,
    blocks: Map<string, BlockView>,
    point: Point,
  ): boolean {
    const standing = trainAt(drawing, review, blocks, point);
    if (standing === null) return false;
    const { train, block } = standing;
    const own =
      blocks.get(block)?.crossing === true
        ? null
        : [...blocks].filter(([, view]) => view.named === train).map(([name]) => name);
    this.held = { train, own, from: point, to: point };
    this.proposal = null;
    return true;
  }

  /** The pointer moved: `true` where what a drop would ask for has changed,
   *  which is when the canvas has something new to draw. */
  moved(drawing: Drawing, review: Review, point: Point): boolean {
    if (this.held === null) return false;
    this.held = { ...this.held, to: point };
    const was = this.proposal;
    this.proposal = this.proposed(drawing, review, point);
    return (
      was?.block !== this.proposal?.block ||
      was?.dest.join() !== this.proposal?.dest.join()
    );
  }

  /** The release: the request to submit, or `null` for a cancel. Either way
   *  the gesture is over. */
  up(drawing: Drawing, review: Review, point: Point): Drop | null {
    if (this.held === null) return null;
    const drop = this.proposed(drawing, review, point);
    this.cancel();
    return drop;
  }

  /** The gesture was abandoned: the pointer was cancelled, or the session it
   *  would have submitted to has gone. */
  cancel(): void {
    this.held = null;
    this.proposal = null;
  }

  /** What a drop at `point` asks for: the block under it in thirds, or
   *  nothing where the drop is one of the train's own blocks, bare paper, or any
   *  block at all for a train that is crossing. */
  private proposed(
    drawing: Drawing,
    review: Review,
    point: Point,
  ): Drop | null {
    if (this.held === null || this.held.own === null) return null;
    const block = blockAt(drawing, review, point);
    if (block === null || this.held.own.includes(block)) return null;
    return { train: this.held.train, block, dest: endsOf(drawing, block, point) };
  }
}

/** Nothing on a run's sheet is drawn out of place: a train's marker moves with
 *  the pointer and the drawing under it does not. */
const STILL: Point = { x: 0, y: 0 };

/** What the run view is painting, as a drag has to read it: the document, what
 *  the store says it means, and where the trains are. Read afresh on each call
 *  rather than captured — the bus moves under a gesture in flight, and a
 *  session may go while one is. */
export interface Painted {
  drawing: Drawing;
  review: Review;
  blocks: Map<string, BlockView>;
  /** symbol → what a click on it asks for, the points the panel offers a
   *  throw on (`scene.pointsOffered`). */
  offered: ReadonlyMap<string, PointWanted>;
}

/**
 * What the run view does with a drag that began on the canvas, handed to the
 * machine below.
 *
 * `submit` and `remove` are the two things a drop of a **marker** can mean.
 * Where the drag began has already said it is a marker's — never the run's
 * state — and where it ended says what it names: a block, or the roster pane,
 * which is nowhere on the railroad
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)).
 * Whether a screen point is over the pane is the view's knowledge, the pane
 * being an element; what it means is here.
 */
export interface Gestures {
  /** What is on screen for a gesture to be about, `null` where nothing is. */
  painted(): Painted | null;
  /** A drop on a block: one `request_wanted`. */
  submit(drop: Drop): void;
  /** A drop on the roster pane: the train comes off the layout. */
  remove(train: string): void;
  /** A click on a point the panel offers: one `point_wanted`. */
  throwPoint(wanted: PointWanted): void;
  /** A click on a widget: what a press on it sends (ADR-0087). */
  pressWidget(name: string): void;
  /** Whether a screen point is over the roster pane. */
  onRoster(screen: Point): boolean;
  /** A tap on a block carrying a train: the train's name, shown there in
   *  place of its photo for a while (#1018). */
  showName(block: string): void;
}

/**
 * The run view's machine as the canvas drives it (model/machine.ts).
 *
 * The same call sequence the editor's `Gesture` is driven by, so the canvas
 * converts pixels to squares once and asks. What a drop asks for is the
 * gesture's; writing it to the bus is the view's, which is why the two
 * handlers are handed in — this model names the train and the ends and
 * nothing else (ADR-0036).
 *
 * A plain left press that takes hold of no train and lands on a point the
 * panel offers is a click on it, if it is released on that point without
 * moving: the point's other position is asked for
 * ([ADR-0068](../../../docs/adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)).
 * A tap on a touch screen need not land on the point: it is a click on the
 * offered point nearest it, within a square, and may move further before it
 * stops being one (#893).
 * A train is taken hold of first, so dragging one across a point throws
 * nothing. A press on a train released within the same slop is a tap: it
 * drops nothing and shows the train's name in the block pressed, where the
 * block shows its photo (#1018).
 *
 * A widget is drawn over the symbols, so a plain left press on one is the
 * widget's before it is a train's or a point's, and a release on the same
 * widget is a click on it (#929): a button or a toggle is pressed, a text
 * widget is not. Power is no part of it, a widget not being the railroad's. What is offered is read again at the release, the bus having
 * moved under the press.
 *
 * `painted` answers `null` while there is nothing to gesture at: no railroad
 * on screen, or no session to submit to. Every call is then quiet, which is
 * the whole of the gate.
 */
export function schedulingMachine(drag: Drag, view: Gestures): Machine {
  const painted = view.painted.bind(view);
  /** The point pressed on and where on screen, while the press may still be
   *  a click on it. */
  let pressed: { symbol: string; screen: Point; touch: boolean } | null = null;
  /** The widget pressed on, while the press may still be a click on it. */
  let widget: { name: string; screen: Point; touch: boolean } | null = null;
  /** The block a train was taken hold of in, while the press may still be a
   *  tap on it. */
  let tapped: { block: string; screen: Point; touch: boolean } | null = null;
  /** The press and the drag both dropped, nothing submitted. */
  function abandon(): Outcome {
    pressed = null;
    widget = null;
    tapped = null;
    if (drag.train === null) return "quiet";
    drag.cancel();
    return "render";
  }
  return {
    down: (point, input) => {
      pressed = null;
      widget = null;
      tapped = null;
      const now = painted();
      if (now === null) return "quiet";
      const name = pressableAt(now.drawing, point);
      if (name !== null) {
        if (input.button === 0 && !input.shift) {
          widget = { name, screen: input.screen, touch: input.touch };
        }
        return "quiet";
      }
      if (drag.down(now.drawing, now.review, now.blocks, point)) {
        const block = blockAt(now.drawing, now.review, point)!;
        tapped = { block, screen: input.screen, touch: input.touch };
        return "render";
      }
      const symbol = input.touch
        ? nearest(now.drawing, now.offered.keys(), point, TOUCH_REACH)
        : under(now.drawing, now.review, point, undefined, true).symbol;
      if (
        input.button === 0 &&
        !input.shift &&
        symbol !== null &&
        now.offered.has(symbol)
      ) {
        pressed = { symbol, screen: input.screen, touch: input.touch };
      }
      return "quiet";
    },
    moved: (point, screen) => {
      if (pressed !== null && strayed(pressed, screen)) pressed = null;
      if (widget !== null && strayed(widget, screen)) widget = null;
      if (tapped !== null && strayed(tapped, screen)) tapped = null;
      const now = painted();
      if (now === null || drag.train === null) return "quiet";
      drag.moved(now.drawing, now.review, point);
      return "render";
    },
    up: (point, screen) => {
      const now = painted();
      const click = pressed;
      pressed = null;
      const tap = tapped;
      tapped = null;
      const on = widget;
      widget = null;
      if (now !== null && on !== null) {
        if (on.touch || pressableAt(now.drawing, point) === on.name) view.pressWidget(on.name);
        return "quiet";
      }
      if (now !== null && click !== null) {
        const wanted = now.offered.get(click.symbol);
        // A tap is held to the slop alone: the release is still the tap, and
        // asking again which point is nearest could name its neighbour.
        const on =
          click.touch ||
          under(now.drawing, now.review, point, undefined, true).symbol === click.symbol;
        if (wanted !== undefined && on) view.throwPoint(wanted);
        return "quiet";
      }
      if (now === null || drag.train === null) return "quiet";
      // Let go over the roster pane, and the train comes off the layout: the
      // marker was dragged out of the picture rather than to somewhere in it.
      // Read before the drop, because the pane is not the canvas and the grid
      // point under it names whatever the viewport happens to have there.
      const held = drag.train;
      if (view.onRoster(screen)) {
        drag.cancel();
        view.remove(held);
        return "render";
      }
      if (tap !== null && !strayed(tap, screen)) {
        drag.cancel();
        view.showName(tap.block);
        return "render";
      }
      const drop = drag.up(now.drawing, now.review, point);
      if (drop !== null) view.submit(drop);
      return "render";
    },
    left: abandon,
    // A second finger: the drag or the throw the first began goes, as a
    // cancel does, and the two fingers move the view instead (#894).
    abandon,
    // The right-click asks the same question of the same point the press does,
    // so the two can never disagree about which train was clicked. A drag the
    // press had started is abandoned: the menu takes the gesture over.
    menu: (point) => {
      const now = painted();
      drag.cancel();
      pressed = null;
      widget = null;
      tapped = null;
      const standing =
        now === null
          ? null
          : trainAt(now.drawing, now.review, now.blocks, point);
      return { outcome: "render", found: standing };
    },
    shift: () => STILL,
    get marks() {
      const { from, to, drop } = drag;
      if (from === null || to === null) return null;
      if (drop === null || painted() === null) return { reach: { from, to } };
      return {
        reach: { from, to },
        target: {
          block: drop.block,
          ends: drop.dest.map((end) => (end.endsWith(".A") ? "A" : "B")),
        },
      };
    },
  };
}

/** Whether the pointer has travelled too far from a press for its release to
 *  be a click: further on a touch screen, a finger rolling as it lifts. */
function strayed(press: { screen: Point; touch: boolean }, screen: Point): boolean {
  return (
    Math.hypot(screen.x - press.screen.x, screen.y - press.screen.y) >
    (press.touch ? TOUCH_SLOP : SLOP)
  );
}

/**
 * The train whose name is on the block under a point, where one is — and that
 * block.
 *
 * A train's name is in every block it holds that reads occupied, whatever the
 * block's colour (model/panel.ts), so one passing from one block to the next
 * answers in both. The press that takes hold of a train and the right-click
 * that offers to turn one around ask this same question of the same point
 * (ui/PANEL.md), so neither can come to disagree about which train was
 * clicked.
 */
export function trainAt(
  drawing: Drawing,
  review: Review,
  blocks: Map<string, BlockView>,
  point: Point,
): { train: string; block: string } | null {
  const block = blockAt(drawing, review, point);
  const train = block === null ? undefined : blocks.get(block)?.named;
  if (block === null || train === undefined) return null;
  return { train, block };
}

/** The block symbol under a point, where the point is on one. The question is
 *  asked in one place for the whole front end (#62), so the answer here is
 *  `under`'s, narrowed to blocks — the only thing a drag can grab or land on.
 *  A drag out of the roster pane asks it too: the pane says where the pointer
 *  let go and what is under it is the drawing's answer (#170). */
export function blockAt(
  drawing: Drawing,
  review: Review,
  point: Point,
): string | null {
  const { symbol, kind } = under(drawing, review, point, undefined, true);
  return kind === "block" ? symbol : null;
}

/**
 * The thirds rule (ui/PANEL.md): where along the block the point falls, read
 * from the block's own A and B pins rather than from the page, so a block that
 * was turned or flipped splits the same way it is wired.
 */
function endsOf(drawing: Drawing, block: string, point: Point): EndRef[] {
  const spec = drawing.symbols[block]!;
  const a = anchorOf(spec, "A");
  const b = anchorOf(spec, "B");
  const [dx, dy] = [b.x - a.x, b.y - a.y];
  const span = dx * dx + dy * dy;
  const along =
    span === 0 ? 0.5 : ((point.x - a.x) * dx + (point.y - a.y) * dy) / span;
  if (along < 1 / 3) return [`${block}.A`];
  if (along > 2 / 3) return [`${block}.B`];
  return [`${block}.A`, `${block}.B`];
}
