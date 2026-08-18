/**
 * What a pointer gesture means: press, drag, band and pan, as EDITOR.md#canvas
 * rules them.
 *
 * The canvas converts the pointer's pixels into squares, calls one method per
 * event, and draws what `band` and `shift` say; every rule after the
 * conversion lives here, where it runs without a DOM (EDITOR.md#tests).
 * Everything that changes the document goes through `Editor`, taken per call
 * and never held, and what happened comes back as an `Outcome` for the
 * component to map onto rendering and events.
 */

import { symbolOf, type PinRef } from "./drawing.js";
import type { Editor } from "./editor.js";
import { anchorOf, faceAt, type Point } from "./geometry.js";
import type { Review } from "./store.js";
import { under, within, type Under } from "./under.js";

/** How far the pointer has to travel, in screen pixels, before a press on a pin
 *  is a drag of its bend rather than the start of a wire. Drawing a wire is
 *  click-then-click rather than a drag, so nothing but a shaky hand is at
 *  stake (EDITOR.md#editing). */
const SLOP = 4;

/** What the caller has to do about a gesture event: nothing, redraw the
 *  gesture visuals, announce that the selection changed, announce that the
 *  document changed, or shift the view by a grid delta — the one effect the
 *  machine cannot apply itself, the viewBox being the component's. */
export type Outcome = "quiet" | "render" | "picked" | "changed" | { pan: Point };

/** What a pointer event says beyond where it is in squares: the button, the
 *  shift key, and the screen pixels — the only frame a slop threshold means
 *  anything in, a square being however many pixels the zoom makes it. */
export interface Input {
  button: number;
  shift: boolean;
  screen: Point;
}

interface Drag {
  from: Point;
  to: Point;
  dx: number;
  dy: number;
}

export interface Band {
  from: Point;
  to: Point;
}

/** A press on a pin, before the pointer has said whether it meant a wire or a
 *  move. */
interface Press {
  pin: PinRef;
  from: Point;
  screen: Point;
}

export class Gesture {
  private press: Press | null = null;
  private drag: Drag | null = null;
  private rubber: Band | null = null;
  private pan: Point | null = null;

  /** The rubber band in flight, for the canvas to draw. */
  get band(): Band | null {
    return this.rubber;
  }

  /** How far a symbol is drawn from where the document puts it, which is
   *  nothing except while a drag of the selection is in progress. */
  shift(editor: Editor, name: string): Point {
    if (this.drag === null || !editor.selection.has(name)) {
      return { x: 0, y: 0 };
    }
    return { x: this.drag.dx, y: this.drag.dy };
  }

  down(editor: Editor, review: Review, point: Point, input: Input): Outcome {
    if (input.button === 1) {
      this.pan = point;
      return "quiet";
    }
    if (input.button !== 0) return "quiet";

    if (editor.pendingFrom !== null) {
      const pin = this.at(editor, review, point).pin;
      if (pin === null) {
        editor.bend(point.x, point.y);
        return "changed";
      }
      return editor.endWire(pin) ? "changed" : "quiet";
    }

    // A press on a pin has not said yet which of the two things it means: a
    // click starts a wire, a drag takes hold of the bend. Held here until the
    // pointer says which (EDITOR.md#editing). Shift-click is the selection
    // gesture throughout, so it skips this and picks up the symbol.
    const { pin, symbol } = this.at(editor, review, point);
    if (pin !== null && !input.shift && editor.free(pin)) {
      this.press = { pin, from: point, screen: input.screen };
      return "quiet";
    }

    if (symbol === null) {
      editor.clearSelection();
      this.rubber = { from: point, to: point };
      return "picked";
    }
    if (!editor.selection.has(symbol)) {
      editor.select([symbol], input.shift);
    } else if (input.shift) {
      editor.select(
        [...editor.selection].filter((name) => name !== symbol),
      );
    }
    this.drag = { from: point, to: point, dx: 0, dy: 0 };
    return "picked";
  }

  moved(editor: Editor, point: Point, screen: Point): Outcome {
    if (this.press !== null) {
      const away = Math.hypot(
        screen.x - this.press.screen.x,
        screen.y - this.press.screen.y,
      );
      if (away <= SLOP) return "quiet";
      const { pin, from } = this.press;
      this.press = null;
      editor.select([symbolOf(pin)]);
      this.drag = { from, to: point, dx: 0, dy: 0 };
      return "picked";
    }

    // The anchor stays put: the view moves under the pointer, so the same
    // screen position reads as the anchor again on the next event.
    if (this.pan !== null) {
      return { pan: { x: this.pan.x - point.x, y: this.pan.y - point.y } };
    }

    // The drag holds its last legal offset while the pointer is over an
    // obstacle, and catches up once the offset is clear again, so a drag across
    // a crowded row is never wasted and never lands on anything. A lone bend
    // follows the faces instead, which are half a square apart.
    if (this.drag !== null) {
      const bend = this.loneBend(editor);
      if (bend !== null) {
        this.drag = { ...this.drag, to: point, ...this.toFace(editor, bend, point) };
        return "render";
      }
      const dx = Math.round(point.x - this.drag.from.x);
      const dy = Math.round(point.y - this.drag.from.y);
      if (!editor.canMove(dx, dy)) return "quiet";
      this.drag = { ...this.drag, to: point, dx, dy };
      return "render";
    }

    if (this.rubber !== null) {
      this.rubber = { ...this.rubber, to: point };
      return "render";
    }
    return "quiet";
  }

  up(editor: Editor, point: Point): Outcome {
    // The press that started this one was on a palette tile, so the drop is
    // the only part of the drag the canvas sees a button for. A drop the
    // ghost showed as blocked writes nothing and ends the drag all the same:
    // the refusal was on screen before the release (EDITOR.md#canvas).
    if (editor.pending !== null) {
      if (editor.dropPending(point.x, point.y) !== null) return "changed";
      editor.cancelPending();
      return "render";
    }

    this.pan = null;
    // A press that never moved: the click it turns out to have been starts a
    // wire at the pin it was on.
    if (this.press !== null) {
      const { pin } = this.press;
      this.press = null;
      editor.startWire(pin);
      return "render";
    }
    if (this.drag !== null) {
      const { to, dx, dy } = this.drag;
      const bend = this.loneBend(editor);
      this.drag = null;
      if (bend !== null) {
        return editor.reface(bend, to.x, to.y) ? "changed" : "render";
      }
      if (dx !== 0 || dy !== 0) {
        editor.move(dx, dy);
        return "changed";
      }
      return "quiet";
    }
    if (this.rubber !== null) {
      const { from, to } = this.rubber;
      this.rubber = null;
      editor.select(within(editor.drawing, from, to));
      return "picked";
    }
    return "quiet";
  }

  /** The pointer left the canvas: a pan or a press in flight is abandoned. A
   *  drag or a band survives, pointer capture keeping leave from firing while
   *  a button is down. */
  left(): Outcome {
    this.pan = null;
    this.press = null;
    return "quiet";
  }

  /**
   * A right-click, told what was clicked. While a palette drag is in flight it
   * abandons the symbol instead of asking about what is under it, and `found`
   * is null: no menu opens (EDITOR.md#palette). A right-click on an unselected
   * symbol selects it first, so the menu applies to what was clicked.
   */
  menu(
    editor: Editor,
    review: Review,
    point: Point,
  ): { outcome: Outcome; found: Under | null } {
    if (editor.pending !== null) {
      editor.cancelPending();
      return { outcome: "render", found: null };
    }
    const found = this.at(editor, review, point);
    if (found.symbol !== null && !editor.selection.has(found.symbol)) {
      editor.select([found.symbol]);
      return { outcome: "picked", found };
    }
    return { outcome: "quiet", found };
  }

  /** What the drawing has under a grid point, drawn where the drag has it. */
  private at(editor: Editor, review: Review, point: Point): Under {
    return under(editor.drawing, review, point, (name) =>
      this.shift(editor, name),
    );
  }

  /** The one bend being dragged, where the selection is exactly that. A bend
   *  moves by face rather than by whole cells, but only on its own: among
   *  others it translates rigidly with them (EDITOR.md#canvas). */
  private loneBend(editor: Editor): string | null {
    const [only, ...rest] = editor.selection;
    if (only === undefined || rest.length > 0) return null;
    return editor.drawing.symbols[only]?.kind === "pin" ? only : null;
  }

  /** How far a bend has to shift to sit on the face nearest a point, which is
   *  what the drag draws until the drop writes it. */
  private toFace(
    editor: Editor,
    name: string,
    point: Point,
  ): { dx: number; dy: number } {
    const spec = editor.drawing.symbols[name]!;
    const { at, rot } = faceAt(point.x, point.y);
    const was = anchorOf(spec, "P");
    const now = anchorOf({ kind: "pin", at, rot }, "P");
    return { dx: now.x - was.x, dy: now.y - was.y };
  }
}
