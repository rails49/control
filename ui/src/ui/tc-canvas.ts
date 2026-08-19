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
import { GESTURING, TRANSIENT, svgFile } from "../model/export.js";
import {
  cellsOf,
  centreOf,
  facePoint,
  gridPointOf,
  labelAnchor,
  labelTurn,
  transformOf,
  type Point,
} from "../model/geometry.js";
import { Gesture, type Outcome } from "../model/gesture.js";
import {
  chosenWay,
  clashes,
  dark,
  lit,
  unpaired,
  type Chosen,
} from "../model/inspect.js";
import { fitBox } from "../model/scene.js";
import type { Review } from "../model/store.js";
import { pointOf, under, type Under } from "../model/under.js";
import { artwork, DEFS } from "../render/artwork.js";
import { BLOCK, FACE, PIN, PORTAL, fitted } from "../render/units.js";
import { canvasStyles, exportStyles } from "./tc-canvas.styles.js";

/** What a canvas with no review yet reads as. */
const EMPTY: Review = {
  red_pins: [],
  unpaired_portals: [],
  junctions: [],
  joints: [],
  layout: null,
  explain: null,
  refused: null,
  offending: [],
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
          <!-- Where a wire can land, marked rather than ruled: a dot on every
               face centre, which is every point faceAt can return and every
               point a pin sits at. Two to a square is the whole lattice, but
               each of the two sits on the tile's own edge and is clipped in
               half by it, so the tile draws all four and each dot is the half
               from this tile beside the half from the one next to it. -->
          <pattern id="faces" width="1" height="1" patternUnits="userSpaceOnUse">
            <circle class="face" cx="0" cy="0.5" r=${FACE} />
            <circle class="face" cx="1" cy="0.5" r=${FACE} />
            <circle class="face" cx="0.5" cy="0" r=${FACE} />
            <circle class="face" cx="0.5" cy="1" r=${FACE} />
          </pattern>
          ${DEFS}
        </defs>
        <rect class="sheet" x=${x} y=${y} width=${w} height=${h} />
        ${this.faces()} ${this.junctions()} ${this.wires()} ${this.symbols()} ${this.pins()}
        ${this.stacked()} ${this.wireline()} ${this.rubberBand()} ${this.ghost()}
      </svg>
    `;
  }

  /** Fit the whole drawing, with a margin. Placement is the document's, so
   *  there is nothing to lay out — only somewhere to look. */
  fit(): void {
    const box = this.getBoundingClientRect();
    const shape = box.width > 0 ? box.height / box.width : 0.7;
    const points: Point[] = [...this.editor.allPins(), ...this.marks()];
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

  /** Where the labels of the portals pairing with nothing are drawn, which
   *  `fit` has to keep on screen. A portal's one pin is on the side away from
   *  its mouth, so the outermost thing in the drawing can be the very mark that
   *  wants looking at, a whole square outside the pin the margin is measured
   *  from. */
  private marks(): Point[] {
    return [...unpaired(this.review ?? EMPTY).keys()].flatMap((name) => {
      const spec = this.editor.drawing.symbols[name];
      return spec === undefined ? [] : [gridPointOf(spec, PORTAL.mark)];
    });
  }

  /**
   * The drawing as a standalone SVG file (model/export.ts).
   *
   * The picture is this component's own markup, cloned. What is on the sheet
   * is composed here and nowhere else, so re-rendering it from the document
   * would be a second composition free to disagree with the screen — the
   * failure mode EDITOR.md#implementation rules out for the netlist.
   *
   * Three things change on the way out. The frame is the whole drawing
   * (`fitBox`) rather than wherever the canvas happens to be looking, so the
   * file does not depend on the view; the sheet, which is drawn to the view,
   * is redrawn to that frame; and the parts that are a gesture in progress go,
   * so the same drawing gives the same bytes whatever is under way.
   */
  exported(): string {
    const box = fitBox(this.editor.drawing);
    const clone = this.renderRoot
      .querySelector("svg")!
      .cloneNode(true) as SVGSVGElement;
    for (const part of TRANSIENT) {
      for (const node of clone.querySelectorAll(part)) node.remove();
    }
    for (const gesturing of GESTURING) {
      for (const node of clone.querySelectorAll(`.${gesturing}`)) {
        node.classList.remove(gesturing);
      }
    }
    // Lit writes a class attribute as its template composes it, blanks and
    // all (`class="pin  "`), so dropping a class would leave the blank where
    // it was and the same drawing would export differently mid-gesture. Every
    // class is written back as its tokens.
    for (const node of clone.querySelectorAll("[class]")) {
      node.setAttribute("class", [...node.classList].join(" "));
    }
    uncomment(clone);
    const sheet = clone.querySelector(".sheet")!;
    sheet.setAttribute("x", String(box.x));
    sheet.setAttribute("y", String(box.y));
    sheet.setAttribute("width", String(box.w));
    sheet.setAttribute("height", String(box.h));
    return svgFile({ box, styles: exportStyles.cssText, body: clone.innerHTML });
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

  /**
   * Where a wire can land, drawn only while one is in flight.
   *
   * A dot sits on every face centre, which is every point `faceAt` can return
   * and every point a pin occupies, so the marks and the landing sites are the
   * same set. They answer a question that is only asked between the click that
   * starts a wire and the one that ends it, so the sheet is bare otherwise.
   */
  private faces(): unknown {
    if (this.editor.pendingFrom === null) return nothing;
    const { x, y, w, h } = this.view;
    return svg`<rect class="faces" x=${x} y=${y} width=${w} height=${h}
                     fill="url(#faces)" />`;
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

  /**
   * The way lit on the drawing, symbol by symbol and leg by leg: the transit
   * chosen in the netlist pane, or the way a refusal is about.
   *
   * Naming the frog that makes two transits exclusive is a claim about the
   * drawing, and this is where it is checked by looking. A refusal is the same
   * kind of claim — it is about a route, and a sentence beside the drawing
   * cannot point at one — so it lights the same way, in the red that means
   * derivation stopped (ADR-0024). The two never arrive together: a drawing
   * that refuses has no netlist to choose from.
   */
  private symbols(): unknown {
    const review = this.review ?? EMPTY;
    const wrong = lit(review.offending);
    const way = wrong.size > 0 ? wrong : lit(chosenWay(review, this.chosen));
    const blind = dark(review);
    const lone = unpaired(review);
    return Object.entries(this.editor.drawing.symbols).map(([name, spec]) => {
      const chosen = this.editor.selection.has(name);
      const shifted = this.shift(name);
      return svg`
        <g
          class=${`symbol ${chosen ? "selected" : ""} ${
            wrong.has(name) ? "offending" : ""
          }`}
          data-symbol=${name}
          transform=${`translate(${shifted.x} ${shifted.y})`}
        >
          <g transform=${transformOf(spec)}>
            ${artwork(spec, way.get(name), blind.get(name))}
          </g>
          ${this.label(name, spec, lone.get(name))}
        </g>
      `;
    });
  }

  /**
   * The text a symbol carries: a block's name always, and the label of a
   * portal that pairs with nothing.
   *
   * A block's label is the only text a *correct* drawing carries
   * (EDITOR.md#symbol-geometry) — every other name is read in the properties
   * dialog and in the netlist pane, portals included. The unpaired portal's
   * label is a finding rather than a name the symbol wears: it is drawn in red
   * and it goes away when the label pairs.
   */
  private label(
    name: string,
    spec: SymbolSpec,
    lone: string | undefined,
  ): unknown {
    if (spec.kind === "portal") return this.portalLabel(spec, lone);
    if (spec.kind !== "block") return nothing;
    return this.blockName(name, spec);
  }

  /**
   * A block's name, centred in its rectangle and turned outside the artwork's
   * own group: upright on a horizontal block and read bottom to top on a
   * vertical one (`labelTurn`).
   *
   * The label turns with the block, so the rectangle's long side is the width
   * it has to fit whichever way the block stands.
   */
  private blockName(name: string, spec: SymbolSpec): unknown {
    const { x, y } = centreOf(spec);
    return svg`<text class="name" x=${x} y=${y}
      font-size=${fitted(name, BLOCK.body.w)}
      transform=${`rotate(${labelTurn(spec)} ${x} ${y})`}>${name}</text>`;
  }

  /**
   * The label a portal that pairs with nothing wears, beside its mouth in red.
   *
   * A lone portal is otherwise invisible twice over: nothing says it pairs
   * with nothing, and nothing says which label it wears, so two of them at
   * opposite ends of the canvas cannot be told from a pair by looking. The
   * mark is therefore the label itself — it names the string to type at the
   * other end, which is what a mark of any other shape would still cost a
   * dialog visit to learn (ADR-0020).
   *
   * Which portals wear one is `/review`'s answer keyed by symbol (inspect.ts);
   * no pairing is worked out here. `gridPointOf` takes the point through the
   * symbol's own flip and quarter turns, so the label sits past the mouth
   * whichever way the portal points and is still drawn upright, and
   * `labelAnchor` starts it at the end nearest the mouth, so a long label runs
   * away from the artwork rather than back across it.
   */
  private portalLabel(spec: SymbolSpec, lone: string | undefined): unknown {
    if (lone === undefined) return nothing;
    const { x, y } = gridPointOf(spec, PORTAL.mark);
    return svg`<text class="unpaired" x=${x} y=${y}
      text-anchor=${labelAnchor(spec, PORTAL.mark)}
      font-size=${PORTAL.mark.size}>${lone}</text>`;
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

  /**
   * The wire following the pointer, ending where the click would land it: on
   * the pin under the pointer, or on the face centre a bend would take.
   *
   * It ends on a mark the sheet already draws rather than under the cursor, so
   * the line is a statement about the drop and not about the mouse. It used to
   * be pulled onto multiples of 15 degrees, which was an aid for laying
   * parallel track — but the drop has always used the raw pointer, so the
   * angle shown could be off by as much as half a square from the one the
   * wire got.
   */
  private wireline(): unknown {
    const from = this.editor.pendingFrom;
    if (from === null || this.pointer === null) return nothing;
    const start = this.point(from);
    if (start === null) return nothing;
    const near = this.at(this.pointer).pin;
    const end =
      near === null
        ? facePoint(this.pointer.x, this.pointer.y)
        : this.point(near);
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


/** Lit's bookkeeping, out of the exported clone: the markers it leaves between
 *  the parts of a template mean nothing in a file, and each carries a number
 *  minted per page load, which would make the same drawing export differently
 *  every session. */
function uncomment(node: Node): void {
  for (const child of [...node.childNodes]) {
    if (child.nodeType === Node.COMMENT_NODE) child.remove();
    else uncomment(child);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-canvas": TcCanvas;
  }
}
