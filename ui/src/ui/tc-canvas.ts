/**
 * The drawing surface: SVG in the DOM, one user unit to one grid square.
 *
 * Hit-testing, hover and selection come from pointer events. Everything that
 * changes the document goes through `Editor`, and what a gesture means is
 * `Gesture`'s (model/gesture.ts): this component converts pixels to squares,
 * feeds the machine one call per event, and maps each outcome onto rendering
 * and events. It holds the machine and a pointer position for the wireline
 * and the ghost, and none of it survives the gesture.
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
  cellsOf,
  centreOf,
  labelTurn,
  snapped,
  transformOf,
  type Point,
} from "../model/geometry.js";
import { Gesture, type Outcome } from "../model/gesture.js";
import { clashes, dark, lit, type Chosen } from "../model/inspect.js";
import type { Review } from "../model/store.js";
import { pointOf, under, type Under } from "../model/under.js";
import { artwork, DEFS } from "../render/artwork.js";
import { BLOCK, PIN, fitted } from "../render/units.js";
import { canvasStyles } from "./styles.js";

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

@customElement("tc-canvas")
export class TcCanvas extends LitElement {
  static override styles = canvasStyles;

  @property({ attribute: false }) editor!: Editor;
  @property({ attribute: false }) review: Review | null = null;
  /** The transit whose way is lit, chosen in the netlist pane. */
  @property({ attribute: false }) chosen: Chosen | null = null;

  @state() private view: Box = { x: -1, y: -1, w: 16, h: 11 };
  @state() private pointer: Point | null = null;
  private gesture = new Gesture();

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

  /**
   * The junctions in trouble, tinted where they are.
   *
   * Every junction used to be tinted, which read as shading behind half the
   * symbols on the sheet while nothing was wrong. Junction membership is read
   * in the netlist pane instead, where a connection's name heads its section
   * above the symbols it is drawn from: a stray wire that merged two throats
   * shows there as one section listing both, rather than as one region where
   * you expected two (EDITOR.md#junctions).
   *
   * What stays is the tint on a name collision, so colour on the canvas means
   * something is wrong. A clash is shown where it is rather than only in a
   * panel, and names are minted, so this is rare and worth looking at.
   *
   * The region carries no name. A junction of one symbol is named after that
   * symbol, so writing the name here put a symbol's own name beside it and
   * read as a label the symbol carried rather than as an overlay.
   */
  private junctions(): unknown {
    const troubled = new Set(
      clashes(this.review ?? EMPTY).flatMap((clash) => clash.where.flat()),
    );
    if (troubled.size === 0) return nothing;
    return (this.review?.junctions ?? []).map((junction) => {
      if (!junction.symbols.some((name) => troubled.has(name))) return nothing;
      const cells = junction.symbols.flatMap((name) => {
        const spec = this.editor.drawing.symbols[name];
        return spec === undefined ? [] : cellsOf(spec);
      });
      if (cells.length === 0) return nothing;
      return svg`
        <g class="junction clashing">
          ${cells.map(
            ([c, r]) => svg`<rect x=${c} y=${r} width="1" height="1" />`,
          )}
        </g>
      `;
    });
  }

  private wires(): unknown {
    return this.editor.drawing.wires.map((wire) => {
      const [a, b] = wirePins(wire);
      const from = this.point(a);
      const to = this.point(b);
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
    const blind = dark(this.review ?? EMPTY);
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
            ${artwork(spec, way.get(name), blind.get(name))}
          </g>
          ${this.label(name, spec)}
        </g>
      `;
    });
  }

  /**
   * A block's label, which is its name, centred in its rectangle and turned
   * outside the artwork's own group: upright on a horizontal block and read
   * bottom to top on a vertical one (`labelTurn`).
   *
   * It is the only text on a symbol (EDITOR.md#symbol-geometry). Other names
   * are read in the properties dialog and in the netlist pane, portals
   * included, and the names over the tinted junction regions are `/review`'s
   * overlay rather than anything a symbol carries.
   *
   * The label turns with the block, so the rectangle's long side is the width
   * it has to fit whichever way the block stands.
   */
  private label(name: string, spec: SymbolSpec): unknown {
    if (spec.kind !== "block") return nothing;
    const { x, y } = centreOf(spec);
    return svg`<text class="name" x=${x} y=${y}
      font-size=${fitted(name, BLOCK.body.w)}
      transform=${`rotate(${labelTurn(spec)} ${x} ${y})`}>${name}</text>`;
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
    const start = this.point(from);
    if (start === null) return nothing;
    const near = this.at(this.pointer).pin;
    const end =
      near === null ? snapped(start, this.pointer) : this.point(near);
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
    const band = this.gesture.band;
    if (band === null) return nothing;
    const { from, to } = band;
    return svg`<rect class="band"
      x=${Math.min(from.x, to.x)} y=${Math.min(from.y, to.y)}
      width=${Math.abs(to.x - from.x)} height=${Math.abs(to.y - from.y)} />`;
  }

  // --- gestures -----------------------------------------------------------

  /** What the machine said back, mapped onto rendering and events. After any
   *  outcome that drew something, a wire in progress wants the pointer: the
   *  wireline starts at the press before the first move arrives. */
  private apply(outcome: Outcome, point: Point): void {
    if (outcome === "quiet") return;
    if (typeof outcome === "object") {
      this.view = {
        ...this.view,
        x: this.view.x + outcome.pan.x,
        y: this.view.y + outcome.pan.y,
      };
      return;
    }
    if (this.editor.pendingFrom !== null) this.pointer = point;
    if (outcome === "picked") this.picked();
    else if (outcome === "changed") this.changed();
    else this.requestUpdate();
  }

  private down(event: PointerEvent): void {
    const point = this.gridAt(event);
    (event.target as Element).setPointerCapture?.(event.pointerId);
    this.apply(
      this.gesture.down(this.editor, this.review ?? EMPTY, point, {
        button: event.button,
        shift: event.shiftKey,
        screen: { x: event.clientX, y: event.clientY },
      }),
      point,
    );
  }

  private moved(event: PointerEvent): void {
    const point = this.gridAt(event);
    // Only the wireline and the ghost read the pointer, and `pointer` is state:
    // assigning it on every move would re-render the whole sheet to draw
    // nothing.
    if (this.editor.pendingFrom !== null || this.editor.pending !== null) {
      this.pointer = point;
    }
    this.apply(
      this.gesture.moved(this.editor, point, {
        x: event.clientX,
        y: event.clientY,
      }),
      point,
    );
  }

  private up(event: PointerEvent): void {
    const point = this.gridAt(event);
    this.apply(this.gesture.up(this.editor, point), point);
  }

  private left(): void {
    this.pointer = null;
    this.gesture.left();
  }

  /**
   * The right-click menu, told what was clicked: the symbol, the junction it
   * belongs to, the joint a wire under the pointer is, and the wire itself.
   * What the click means is `Gesture`'s ruling; a null `found` is a right
   * button that ended a palette drag instead, so no menu opens.
   */
  private menu(event: MouseEvent): void {
    event.preventDefault();
    const point = this.gridAt(event);
    const { outcome, found } = this.gesture.menu(
      this.editor,
      this.review ?? EMPTY,
      point,
    );
    this.apply(outcome, point);
    if (found === null) return;
    this.dispatchEvent(
      new CustomEvent("canvas-menu", {
        detail: { x: event.clientX, y: event.clientY, ...found },
        bubbles: true,
        composed: true,
      }),
    );
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

  /**
   * What the drawing has under a grid point.
   *
   * The rules live in `under` (model/under.ts): a pin beats the symbol
   * carrying it, a wire is offered only where no symbol is. The drag offset
   * goes in as a function, so a click lands on what is drawn rather than on
   * what the document says.
   */
  private at(point: Point): Under {
    return under(this.editor.drawing, this.review ?? EMPTY, point, (name) =>
      this.shift(name),
    );
  }

  /** Where a pin is drawn, which is where a wire has to end. */
  private point(pin: PinRef): Point | null {
    return pointOf(this.editor.drawing, pin, (name) => this.shift(name));
  }

  /** How far a symbol is drawn from where the document puts it, which the
   *  machine knows: nothing except while a drag of the selection is in
   *  progress. */
  private shift(name: string): Point {
    return this.gesture.shift(this.editor, name);
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


declare global {
  interface HTMLElementTagNameMap {
    "tc-canvas": TcCanvas;
  }
}
