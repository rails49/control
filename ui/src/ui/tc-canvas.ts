/**
 * The drawing surface: SVG in the DOM, one user unit to one grid square.
 *
 * Hit-testing, hover and selection come from pointer events; live state is a
 * class toggle. Everything that changes the document goes through `Editor`, so
 * this component holds only what is true of a gesture in progress — where the
 * pointer is, how far a drag has come, the rubber band — and none of it
 * survives the gesture.
 */

import { LitElement, html, svg, nothing, type SVGTemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import {
  symbolOf,
  wirePins,
  type PinRef,
  type SymbolSpec,
} from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import {
  anchorOf,
  cellsOf,
  centreOf,
  faceAt,
  snapped,
  transformOf,
  type Point,
} from "../model/geometry.js";
import { clashes, lit, type Chosen } from "../model/inspect.js";
import type { Joint, Review } from "../model/store.js";
import { artwork, DEFS } from "../render/artwork.js";
import { PIN } from "../render/units.js";
import { canvasStyles } from "./styles.js";

const HIT = 0.22; // how near a pointer has to come to a pin, in squares

/** How far the pointer has to travel, in screen pixels, before a press on a pin
 *  is a drag of its bend rather than the start of a wire. Drawing a wire is
 *  click-then-click rather than a drag, so nothing but a shaky hand is at
 *  stake (EDITOR.md#editing). */
const SLOP = 4;

/** What a canvas with no review yet reads as. */
const EMPTY: Review = {
  red_pins: [],
  junctions: [],
  joints: [],
  layout: null,
  explain: null,
  refused: null,
};

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Drag {
  from: Point;
  to: Point;
  dx: number;
  dy: number;
}

interface Band {
  from: Point;
  to: Point;
}

/** A press on a pin, before the pointer has said whether it meant a wire or a
 *  move. `screen` is in pixels, the only frame a slop threshold means anything
 *  in: a square is however many pixels the zoom makes it. */
interface Press {
  pin: PinRef;
  from: Point;
  screen: Point;
}

@customElement("tc-canvas")
export class TcCanvas extends LitElement {
  static override styles = canvasStyles;

  @property({ attribute: false }) editor!: Editor;
  @property({ attribute: false }) review: Review | null = null;
  /** The transit whose way is lit, chosen in the netlist pane. */
  @property({ attribute: false }) chosen: Chosen | null = null;

  @state() private view: Box = { x: -1, y: -1, w: 16, h: 11 };
  @state() private pointer: Point | null = null;
  @state() private drag: Drag | null = null;
  @state() private band: Band | null = null;
  @state() private pan: Point | null = null;
  private press: Press | null = null;

  private watch = new ResizeObserver(() => this.square());

  override connectedCallback(): void {
    super.connectedCallback();
    this.watch.observe(this);
  }

  override disconnectedCallback(): void {
    this.watch.disconnect();
    super.disconnectedCallback();
  }

  override render() {
    const { x, y, w, h } = this.view;
    return html`
      <svg
        viewBox=${`${x} ${y} ${w} ${h}`}
        @pointerdown=${this.down}
        @pointermove=${this.moved}
        @pointerup=${this.up}
        @pointerleave=${this.left}
        @wheel=${this.wheel}
        @contextmenu=${this.menu}
      >
        <defs>
          <pattern id="grid" width="1" height="1" patternUnits="userSpaceOnUse">
            <path class="grid" d="M1 0 V1 H0" />
          </pattern>
          ${DEFS}
        </defs>
        <rect class="sheet" x=${x} y=${y} width=${w} height=${h} />
        <rect
          class="squares"
          x=${x}
          y=${y}
          width=${w}
          height=${h}
          fill="url(#grid)"
        />
        ${this.junctions()} ${this.wires()} ${this.symbols()} ${this.pins()}
        ${this.stacked()} ${this.wireline()} ${this.rubberBand()} ${this.ghost()}
      </svg>
    `;
  }

  /** Fit the whole drawing, with a margin. Placement is the document's, so
   *  there is nothing to lay out — only somewhere to look. */
  fit(): void {
    const box = this.getBoundingClientRect();
    const shape = box.width > 0 ? box.height / box.width : 0.7;
    const points = this.editor.allPins();
    if (points.length === 0) {
      this.view = { x: -1, y: -1, w: 16, h: 16 * shape };
      return;
    }
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const [x, y] = [Math.min(...xs) - 1, Math.min(...ys) - 1];
    const [across, down] = [Math.max(...xs) - x + 1, Math.max(...ys) - y + 1];
    const w = Math.max(across, down / shape);
    const h = w * shape;
    this.view = { x: x - (w - across) / 2, y: y - (h - down) / 2, w, h };
  }

  /** Zoom about the middle of the view, which is what a button can mean —
   *  the wheel zooms about the pointer, having one. */
  zoom(scale: number): void {
    const { x, y, w, h } = this.view;
    this.view = {
      x: x + (w * (1 - scale)) / 2,
      y: y + (h * (1 - scale)) / 2,
      w: w * scale,
      h: h * scale,
    };
  }

  /** Keep a grid square square: the viewBox takes the element's own shape, so
   *  the sheet fills it and a wheel zoom scales both ways at once. */
  private square(): void {
    const box = this.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return;
    const wanted = (this.view.w * box.height) / box.width;
    if (Math.abs(wanted - this.view.h) > 1e-6) {
      this.view = { ...this.view, h: wanted };
    }
  }

  // --- what is drawn ------------------------------------------------------

  /** A junction is a connected group of non-block symbols, which `/review`
   *  computes. Tinting it as one region is what makes a stray wire that
   *  merged two throats visible long before it is a wrong concurrency pair. */
  private junctions(): unknown {
    // A name collision is shown at the edit that caused it (EDITOR.md), and
    // where it is is the region wearing the name, not a sentence in a panel.
    const troubled = new Set(
      clashes(this.review ?? EMPTY).flatMap((clash) => clash.where.flat()),
    );
    return (this.review?.junctions ?? []).map((junction, index) => {
      const cells = junction.symbols.flatMap((name) => {
        const spec = this.editor.drawing.symbols[name];
        return spec === undefined ? [] : cellsOf(spec);
      });
      if (cells.length === 0) return nothing;
      const left = Math.min(...cells.map(([c]) => c));
      const top = Math.min(...cells.map(([, r]) => r));
      const wrong = junction.symbols.some((name) => troubled.has(name));
      return svg`
        <g class=${`junction tint-${index % 6} ${wrong ? "clashing" : ""}`}>
          ${cells.map(
            ([c, r]) => svg`<rect x=${c} y=${r} width="1" height="1" />`,
          )}
          <text x=${left + 0.1} y=${top - 0.15}>${
            junction.name ?? (junction.names.join(" / ") || "unnamed")
          }</text>
        </g>
      `;
    });
  }

  private wires(): unknown {
    return this.editor.drawing.wires.map((wire) => {
      const [a, b] = wirePins(wire);
      const from = this.pointOf(a);
      const to = this.pointOf(b);
      if (from === null || to === null) return nothing;
      return svg`<line class="wire" x1=${from.x} y1=${from.y}
                       x2=${to.x} y2=${to.y} />`;
    });
  }

  /** The way a chosen transit takes, symbol by symbol and leg by leg. Naming
   *  the frog that makes two transits exclusive is a claim about the drawing,
   *  and this is where it is checked by looking. */
  private symbols(): unknown {
    const way = lit(this.review ?? EMPTY, this.chosen);
    return Object.entries(this.editor.drawing.symbols).map(([name, spec]) => {
      const chosen = this.editor.selection.has(name);
      const shifted = this.shift(name);
      return svg`
        <g
          class=${`symbol ${chosen ? "selected" : ""}`}
          data-symbol=${name}
          transform=${`translate(${shifted.x} ${shifted.y})`}
        >
          <g transform=${transformOf(spec)}>
            ${artwork(spec, way.get(name))}
          </g>
          ${this.label(name, spec)}
        </g>
      `;
    });
  }

  /**
   * A block's label, centred in its rectangle and drawn upright outside the
   * turned group, where a quarter turn would stand it on its side.
   *
   * It is the only text on a symbol (EDITOR.md#symbol-geometry). A name is read
   * in the properties dialog and in the netlist pane instead, portals included,
   * and the names over the tinted junction regions are `/review`'s overlay
   * rather than anything a symbol carries.
   */
  private label(name: string, spec: SymbolSpec): unknown {
    if (spec.kind !== "block") return nothing;
    const { x, y } = centreOf(spec);
    return svg`<text class="name" x=${x} y=${y}>${spec.label || name}</text>`;
  }

  /** Every pin, green where `/review` is satisfied with it and red where it is
   *  not. The front end computes no topology, so which are red is the store's
   *  answer and not this component's. */
  private pins(): unknown {
    const red = new Set(this.review?.red_pins ?? []);
    return this.editor.allPins().map(({ pin, x, y }) => {
      const shifted = this.shift(symbolOf(pin));
      const pending = this.editor.pendingFrom === pin;
      return svg`<circle
        class=${`pin ${red.has(pin) ? "red" : ""} ${pending ? "pending" : ""}`}
        data-pin=${pin}
        cx=${x + shifted.x}
        cy=${y + shifted.y}
        r=${PIN}
      />`;
    });
  }

  /** The squares more than one symbol covers, marked over the artwork.
   *  Placing and dragging cannot make one; rotate and flip can, and this is
   *  where they say so (EDITOR.md#canvas). */
  private stacked(): unknown {
    return this.editor.overlaps().map(
      ({ cell: [c, r] }) =>
        svg`<rect class="stacked" x=${c} y=${r} width="1" height="1" />`,
    );
  }

  /** The wire following the pointer, softly snapped to multiples of 15
   *  degrees. A click on a pin overrides the snap: the wire takes whatever
   *  angle its two pins give it. */
  private wireline(): unknown {
    const from = this.editor.pendingFrom;
    if (from === null || this.pointer === null) return nothing;
    const start = this.pointOf(from);
    if (start === null) return nothing;
    const near = this.pinNear(this.pointer);
    const end =
      near === null ? snapped(start, this.pointer) : this.pointOf(near);
    if (end === null) return nothing;
    return svg`<line class="wireline" x1=${start.x} y1=${start.y}
                     x2=${end.x} y2=${end.y} />`;
  }

  /**
   * The symbol being dragged out of the palette, drawn where it would land.
   *
   * It is the artwork the placed symbol will have, on the grid it will sit on,
   * so what a drop does is visible before the drop: the ghost snaps cell by
   * cell, `r` and `f` turn it under the pointer, and the squares another
   * symbol already has are tinted — those squares and not the whole footprint,
   * so the one in the way is the one the eye goes to, rather than the drop
   * failing silently (EDITOR.md#canvas). Off the canvas there is no pointer
   * and nothing is drawn, there being nowhere to place it there.
   */
  private ghost(): unknown {
    const pending = this.editor.pending;
    if (pending === null || this.pointer === null) return nothing;
    const landing = this.editor.placementAt(this.pointer.x, this.pointer.y);
    if (landing === null) return nothing;
    const spec = { ...pending, at: landing.at };
    const blocked = landing.blocked.length > 0;
    return svg`
      <g class=${`ghost ${blocked ? "blocked" : ""}`}>
        ${landing.blocked.map(
          ([c, r]) => svg`<rect class="stacked" x=${c} y=${r}
                                width="1" height="1" />`,
        )}
        <g transform=${transformOf(spec)}>${artwork(spec)}</g>
      </g>
    `;
  }

  private rubberBand(): SVGTemplateResult | typeof nothing {
    if (this.band === null) return nothing;
    const { from, to } = this.band;
    return svg`<rect class="band"
      x=${Math.min(from.x, to.x)} y=${Math.min(from.y, to.y)}
      width=${Math.abs(to.x - from.x)} height=${Math.abs(to.y - from.y)} />`;
  }

  // --- gestures -----------------------------------------------------------

  private down(event: PointerEvent): void {
    const point = this.gridAt(event);
    (event.target as Element).setPointerCapture?.(event.pointerId);

    if (event.button === 1) {
      this.pan = point;
      return;
    }
    if (event.button !== 0) return;

    if (this.editor.pendingFrom !== null) {
      const pin = this.pinNear(point);
      if (pin === null) {
        this.editor.bend(point.x, point.y);
        this.changed();
      } else if (this.editor.endWire(pin)) {
        this.changed();
      }
      return;
    }

    // A press on a pin has not said yet which of the two things it means: a
    // click starts a wire, a drag takes hold of the bend. Held here until the
    // pointer says which (EDITOR.md#editing). Shift-click is the selection
    // gesture throughout, so it skips this and picks up the symbol.
    const pin = this.pinNear(point);
    if (pin !== null && !event.shiftKey && this.editor.free(pin)) {
      this.press = { pin, from: point, screen: { x: event.clientX, y: event.clientY } };
      return;
    }

    const symbol = pin === null ? this.symbolAt(point) : symbolOf(pin);
    if (symbol === null) {
      this.editor.clearSelection();
      this.band = { from: point, to: point };
      this.picked();
      return;
    }
    if (!this.editor.selection.has(symbol)) {
      this.editor.select([symbol], event.shiftKey);
    } else if (event.shiftKey) {
      this.editor.select(
        [...this.editor.selection].filter((name) => name !== symbol),
      );
    }
    this.drag = { from: point, to: point, dx: 0, dy: 0 };
    this.picked();
  }

  private moved(event: PointerEvent): void {
    const point = this.gridAt(event);
    // Only the wireline and the ghost read the pointer, and `pointer` is state:
    // assigning it on every move would re-render the whole sheet to draw
    // nothing.
    if (this.editor.pendingFrom !== null || this.editor.pending !== null) {
      this.pointer = point;
    }

    if (this.press !== null) {
      const away = Math.hypot(
        event.clientX - this.press.screen.x,
        event.clientY - this.press.screen.y,
      );
      if (away > SLOP) {
        const { pin, from } = this.press;
        this.press = null;
        this.editor.select([symbolOf(pin)]);
        this.drag = { from, to: point, dx: 0, dy: 0 };
        this.picked();
      }
      return;
    }

    if (this.pan !== null) {
      this.view = {
        ...this.view,
        x: this.view.x - (point.x - this.pan.x),
        y: this.view.y - (point.y - this.pan.y),
      };
      return;
    }
    // The drag holds its last legal offset while the pointer is over an
    // obstacle, and catches up once the offset is clear again, so a drag across
    // a crowded row is never wasted and never lands on anything. A lone bend
    // follows the faces instead, which are half a square apart.
    if (this.drag !== null) {
      const bend = this.loneBend();
      if (bend !== null) {
        this.drag = { ...this.drag, to: point, ...this.toFace(bend, point) };
        return;
      }
      const dx = Math.round(point.x - this.drag.from.x);
      const dy = Math.round(point.y - this.drag.from.y);
      if (this.editor.canMove(dx, dy)) this.drag = { ...this.drag, to: point, dx, dy };
      return;
    }
    if (this.band !== null) this.band = { ...this.band, to: point };
  }

  private up(event: PointerEvent): void {
    // The press that started this one was on a palette tile, so the drop is
    // the only part of the drag the canvas sees a button for. A drop the
    // ghost showed as blocked writes nothing and ends the drag all the same:
    // the refusal was on screen before the release (EDITOR.md#canvas).
    if (this.editor.pending !== null) {
      const point = this.gridAt(event);
      if (this.editor.dropPending(point.x, point.y) !== null) this.changed();
      else this.editor.cancelPending();
      this.requestUpdate();
      return;
    }

    this.pan = null;
    // A press that never moved: the click it turns out to have been starts a
    // wire at the pin it was on.
    if (this.press !== null) {
      const { pin, from } = this.press;
      this.press = null;
      this.editor.startWire(pin);
      this.pointer = from;
      this.requestUpdate();
      return;
    }
    if (this.drag !== null) {
      const { to, dx, dy } = this.drag;
      const bend = this.loneBend();
      this.drag = null;
      if (bend !== null) {
        if (this.editor.reface(bend, to.x, to.y)) this.changed();
        return;
      }
      if (dx !== 0 || dy !== 0) {
        this.editor.move(dx, dy);
        this.changed();
        return;
      }
    }
    if (this.band !== null) {
      const { from, to } = this.band;
      this.band = null;
      this.editor.select(this.within(from, to));
      this.picked();
    }
  }

  private left(): void {
    this.pointer = null;
    this.pan = null;
    this.press = null;
  }

  /** The one bend being dragged, where the selection is exactly that. A bend
   *  moves by face rather than by whole cells, but only on its own: among
   *  others it translates rigidly with them (EDITOR.md#canvas). */
  private loneBend(): string | null {
    const [only, ...rest] = this.editor.selection;
    if (only === undefined || rest.length > 0) return null;
    return this.editor.drawing.symbols[only]?.kind === "pin" ? only : null;
  }

  /** How far a bend has to shift to sit on the face nearest a point, which is
   *  what the drag draws until the drop writes it. */
  private toFace(name: string, point: Point): { dx: number; dy: number } {
    const spec = this.editor.drawing.symbols[name]!;
    const { at, rot } = faceAt(point.x, point.y);
    const was = anchorOf(spec, "P");
    const now = anchorOf({ kind: "pin", at, rot }, "P");
    return { dx: now.x - was.x, dy: now.y - was.y };
  }

  /**
   * The right-click menu, told what was clicked: the symbol, the junction it
   * belongs to, and the joint a wire under the pointer is. All three come from
   * `/review`, so nothing here works out what anything means.
   */
  private menu(event: MouseEvent): void {
    event.preventDefault();
    // The right button is one of the three ways out of a drag, so while one is
    // in flight it abandons the symbol instead of asking about what is under
    // it (EDITOR.md#palette).
    if (this.editor.pending !== null) {
      this.editor.cancelPending();
      this.requestUpdate();
      return;
    }
    const point = this.gridAt(event);
    const pin = this.pinNear(point);
    const symbol = pin === null ? this.symbolAt(point) : symbolOf(pin);
    if (symbol !== null && !this.editor.selection.has(symbol)) {
      this.editor.select([symbol]);
      this.picked();
    }
    const junction =
      symbol === null
        ? null
        : (this.review?.junctions ?? []).find((one) =>
            one.symbols.includes(symbol),
          ) ?? null;
    this.dispatchEvent(
      new CustomEvent("canvas-menu", {
        detail: {
          x: event.clientX,
          y: event.clientY,
          symbol,
          junction,
          joint: this.jointNear(point),
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** The joint whose drawn line passes nearest the pointer, where one does.
   *  A joint has no symbol to click, only its wires. */
  private jointNear(point: Point): Joint | null {
    let best: { joint: Joint; away: number } | null = null;
    for (const joint of this.review?.joints ?? []) {
      for (const [a, b] of joint.wires) {
        const from = this.pointOf(a);
        const to = this.pointOf(b);
        if (from === null || to === null) continue;
        const away = awayFrom(point, from, to);
        if (away <= HIT && (best === null || away < best.away)) {
          best = { joint, away };
        }
      }
    }
    return best?.joint ?? null;
  }

  private wheel(event: WheelEvent): void {
    event.preventDefault();
    const point = this.gridAt(event);
    const scale = Math.exp(event.deltaY / 400);
    this.view = {
      x: point.x - (point.x - this.view.x) * scale,
      y: point.y - (point.y - this.view.y) * scale,
      w: this.view.w * scale,
      h: this.view.h * scale,
    };
  }

  // --- reading the drawing under the pointer ------------------------------

  private gridAt(event: MouseEvent): Point {
    const svgElement = this.renderRoot.querySelector("svg")!;
    const matrix = svgElement.getScreenCTM();
    if (matrix === null) return { x: 0, y: 0 };
    const point = svgElement.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const grid = point.matrixTransform(matrix.inverse());
    return { x: grid.x, y: grid.y };
  }

  private pinNear(point: Point): PinRef | null {
    let best: { pin: PinRef; away: number } | null = null;
    for (const { pin, x, y } of this.editor.allPins()) {
      const shifted = this.shift(symbolOf(pin));
      const away = Math.hypot(x + shifted.x - point.x, y + shifted.y - point.y);
      if (away <= HIT && (best === null || away < best.away)) {
        best = { pin, away };
      }
    }
    return best?.pin ?? null;
  }

  private symbolAt(point: Point): string | null {
    const [c, r] = [Math.floor(point.x), Math.floor(point.y)];
    for (const [name, spec] of Object.entries(this.editor.drawing.symbols)) {
      const shifted = this.shift(name);
      const covers = cellsOf(spec).some(
        ([cx, cy]) => cx + shifted.x === c && cy + shifted.y === r,
      );
      if (covers) return name;
    }
    return null;
  }

  private within(from: Point, to: Point): string[] {
    const [x0, x1] = [Math.min(from.x, to.x), Math.max(from.x, to.x)];
    const [y0, y1] = [Math.min(from.y, to.y), Math.max(from.y, to.y)];
    return Object.entries(this.editor.drawing.symbols)
      .filter(([, spec]) => {
        const { x, y } = centreOf(spec);
        return x >= x0 && x <= x1 && y >= y0 && y <= y1;
      })
      .map(([name]) => name);
  }

  private pointOf(pin: PinRef): Point | null {
    const spec = this.editor.drawing.symbols[symbolOf(pin)];
    if (spec === undefined) return null;
    const { x, y } = anchorOf(spec, pin.slice(pin.indexOf(".") + 1));
    const shifted = this.shift(symbolOf(pin));
    return { x: x + shifted.x, y: y + shifted.y };
  }

  /** How far a symbol is drawn from where the document puts it, which is
   *  nothing except while a drag of the selection is in progress. */
  private shift(name: string): Point {
    if (this.drag === null || !this.editor.selection.has(name)) {
      return { x: 0, y: 0 };
    }
    return { x: this.drag.dx, y: this.drag.dy };
  }

  private changed(): void {
    this.requestUpdate();
    this.dispatchEvent(new CustomEvent("edit", { bubbles: true, composed: true }));
  }

  /** The selection changed, the document not. The netlist pane inspects the
   *  one selected symbol, so the editor has to hear about it: the canvas holds
   *  the same `Editor` across the change, and Lit sees no changed property. */
  private picked(): void {
    this.requestUpdate();
    this.dispatchEvent(
      new CustomEvent("picked", { bubbles: true, composed: true }),
    );
  }
}


/** How far a point lies from a line segment. */
function awayFrom(point: Point, from: Point, to: Point): number {
  const [dx, dy] = [to.x - from.x, to.y - from.y];
  const span = dx * dx + dy * dy;
  const along =
    span === 0
      ? 0
      : Math.max(
          0,
          Math.min(
            1,
            ((point.x - from.x) * dx + (point.y - from.y) * dy) / span,
          ),
        );
  return Math.hypot(from.x + along * dx - point.x, from.y + along * dy - point.y);
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-canvas": TcCanvas;
  }
}
