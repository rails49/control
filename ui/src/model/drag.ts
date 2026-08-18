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
 * the cancel gesture and not a judgement about feasibility.
 *
 * The departure end is no part of this: it is the train's facing, which the
 * panel model holds and supplies when it composes the request (ADR-0019).
 */

import type { Drawing } from "./drawing.js";
import { anchorOf, type Point } from "./geometry.js";
import type { BlockView } from "./panel.js";
import type { Review } from "./store.js";
import { under } from "./under.js";

/** What a drop asks for: one block, and the ends the train may enter through
 *  — one for an outer third, both for the middle. */
export interface Drop {
  train: string;
  block: string;
  dest: string[];
}

interface Held {
  train: string;
  /** The block the train stands in, which is the drop that cancels. */
  block: string;
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

  /** A press: it takes hold only where a train stands. */
  down(
    drawing: Drawing,
    review: Review,
    blocks: Map<string, BlockView>,
    point: Point,
  ): boolean {
    const block = blockAt(drawing, review, point);
    const view = block === null ? undefined : blocks.get(block);
    if (block === null || view?.train === undefined || view.state !== "occupied") {
      return false;
    }
    this.held = { train: view.train, block, from: point, to: point };
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

  /** The pointer left, or the gesture was abandoned. */
  cancel(): void {
    this.held = null;
    this.proposal = null;
  }

  /** What a drop at `point` asks for: the block under it in thirds, or
   *  nothing where the drop is the train's own block or bare paper. */
  private proposed(
    drawing: Drawing,
    review: Review,
    point: Point,
  ): Drop | null {
    if (this.held === null) return null;
    const block = blockAt(drawing, review, point);
    if (block === null || block === this.held.block) return null;
    return { train: this.held.train, block, dest: endsOf(drawing, block, point) };
  }
}

/** The block symbol under a point, where the point is on one. The question is
 *  asked in one place for the whole front end (#62), so the answer here is
 *  `under`'s, narrowed to blocks — the only thing a drag can grab or land on. */
function blockAt(drawing: Drawing, review: Review, point: Point): string | null {
  const { symbol, kind } = under(drawing, review, point);
  return kind === "block" ? symbol : null;
}

/**
 * The thirds rule (ui/PANEL.md): where along the block the point falls, read
 * from the block's own A and B pins rather than from the page, so a block that
 * was turned or flipped splits the same way it is wired.
 */
function endsOf(drawing: Drawing, block: string, point: Point): string[] {
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
