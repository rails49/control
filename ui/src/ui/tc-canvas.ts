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

import type { Kind } from "../symbols.generated.js";
import { symbolOf, wirePins, type PinRef } from "../model/drawing.js";
import { Editor } from "../model/editor.js";
import {
  anchorOf,
  cellsOf,
  centreOf,
  placed,
  snapped,
  transformOf,
  type Point,
} from "../model/geometry.js";
import type { Joint, Review } from "../model/store.js";
import { artwork } from "../render/artwork.js";
import { canvasStyles } from "./styles.js";
import type { Chosen } from "./tc-netlist.js";

const HIT = 0.22; // how near a pointer has to come to a pin, in squares

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Drag {
  from: Point;
  dx: number;
  dy: number;
}

interface Band {
  from: Point;
  to: Point;
}

@customElement("tc-canvas")
export class TcCanvas extends LitElement {
  static override styles = canvasStyles;

  @property({ attribute: false }) editor!: Editor;
  @property({ attribute: false }) review: Review | null = null;
  /** The palette kind the next click places, if the palette is armed. */
  @property({ attribute: false }) placing: Kind | null = null;
  /** The transit whose way is lit, chosen in the netlist pane. */
  @property({ attribute: false }) chosen: Chosen | null = null;

  @state() private view: Box = { x: -1, y: -1, w: 16, h: 11 };
  @state() private pointer: Point | null = null;
  @state() private drag: Drag | null = null;
  @state() private band: Band | null = null;
  @state() private pan: Point | null = null;

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
        ${this.wireline()} ${this.rubberBand()}
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
    return (this.review?.junctions ?? []).map((junction, index) => {
      const cells = junction.symbols.flatMap((name) => {
        const spec = this.editor.drawing.symbols[name];
        return spec === undefined ? [] : cellsOf(spec);
      });
      if (cells.length === 0) return nothing;
      const left = Math.min(...cells.map(([c]) => c));
      const top = Math.min(...cells.map(([, r]) => r));
      return svg`
        <g class=${`junction tint-${index % 6}`}>
          ${cells.map(
            ([c, r]) => svg`<rect x=${c} y=${r} width="1" height="1" />`,
          )}
          <text x=${left + 0.1} y=${top - 0.15}>${junction.name ?? "unnamed"}</text>
        </g>
      `;
    });
  }

  /** The way a chosen transit takes, symbol by symbol and leg by leg. Naming
   *  the frog that makes two transits exclusive is a claim about the drawing,
   *  and this is where it is checked by looking. */
  private lit(): Set<string> {
    if (this.chosen === null) return new Set();
    const way = this.review?.explain?.connections[this.chosen.connection]
      ?.transits[this.chosen.transit]?.way;
    return new Set((way ?? []).map(([symbol]) => symbol));
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

  private symbols(): unknown {
    const lit = this.lit();
    return Object.entries(this.editor.drawing.symbols).map(([name, spec]) => {
      const chosen = this.editor.selection.has(name);
      const shifted = this.shift(name);
      // The label is drawn upright below the symbol rather than inside the
      // turned group, where a quarter turn would stand it on its side.
      const label = spec.label || name;
      const centre = centreOf(spec);
      const below = centre.y + placed(spec).footprint.h / 2 + 0.32;
      return svg`
        <g
          class=${`symbol ${chosen ? "selected" : ""} ${lit.has(name) ? "lit" : ""}`}
          data-symbol=${name}
          transform=${`translate(${shifted.x} ${shifted.y})`}
        >
          <g transform=${transformOf(spec)}>${artwork(spec)}</g>
          ${
            spec.kind === "pin"
              ? nothing
              : svg`<text class="name" x=${centre.x} y=${below}>${label}</text>`
          }
        </g>
      `;
    });
  }

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
        r="0.09"
      />`;
    });
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

    if (this.placing !== null) {
      this.editor.place(this.placing, [
        Math.floor(point.x),
        Math.floor(point.y),
      ]);
      this.changed();
      return;
    }

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

    // Shift-click is the selection gesture throughout, so it picks up a pin's
    // symbol rather than starting a wire. It is the only way to take hold of a
    // bend that still has room for a second wire, which is the state a bend
    // spends most of an edit in.
    const pin = this.pinNear(point);
    if (pin !== null && !event.shiftKey && this.editor.free(pin)) {
      this.editor.startWire(pin);
      this.pointer = point;
      this.requestUpdate();
      return;
    }

    const symbol = pin === null ? this.symbolAt(point) : symbolOf(pin);
    if (symbol === null) {
      this.editor.clearSelection();
      this.band = { from: point, to: point };
      this.requestUpdate();
      return;
    }
    if (!this.editor.selection.has(symbol)) {
      this.editor.select([symbol], event.shiftKey);
    } else if (event.shiftKey) {
      this.editor.select(
        [...this.editor.selection].filter((name) => name !== symbol),
      );
    }
    this.drag = { from: point, dx: 0, dy: 0 };
    this.requestUpdate();
  }

  private moved(event: PointerEvent): void {
    const point = this.gridAt(event);
    // Only the wireline reads the pointer, and `pointer` is state: assigning
    // it on every move would re-render the whole sheet to draw nothing.
    if (this.editor.pendingFrom !== null) this.pointer = point;

    if (this.pan !== null) {
      this.view = {
        ...this.view,
        x: this.view.x - (point.x - this.pan.x),
        y: this.view.y - (point.y - this.pan.y),
      };
      return;
    }
    if (this.drag !== null) {
      this.drag = {
        ...this.drag,
        dx: Math.round(point.x - this.drag.from.x),
        dy: Math.round(point.y - this.drag.from.y),
      };
      return;
    }
    if (this.band !== null) this.band = { ...this.band, to: point };
  }

  private up(): void {
    this.pan = null;
    if (this.drag !== null) {
      const { dx, dy } = this.drag;
      this.drag = null;
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
      this.requestUpdate();
    }
  }

  private left(): void {
    this.pointer = null;
    this.pan = null;
  }

  /**
   * The right-click menu, told what was clicked: the symbol, the junction it
   * belongs to, and the joint a wire under the pointer is. All three come from
   * `/review`, so nothing here works out what anything means.
   */
  private menu(event: MouseEvent): void {
    event.preventDefault();
    const point = this.gridAt(event);
    const pin = this.pinNear(point);
    const symbol = pin === null ? this.symbolAt(point) : symbolOf(pin);
    if (symbol !== null && !this.editor.selection.has(symbol)) {
      this.editor.select([symbol]);
      this.requestUpdate();
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
