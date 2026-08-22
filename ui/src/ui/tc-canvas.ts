/**
 * The drawing surface, in either of its two modes: SVG in the DOM, one user
 * unit to one grid square
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * There is one railroad and two views of it, so there is one canvas. The
 * viewport — zoom, the wheel, the middle-button pan and fit — is the same for
 * both and is this component's, and so are the artwork, the wires and where
 * every symbol sits. `mode` decides what only one of them draws: **edit**
 * has the pins, the face marks a wire in flight asks for, the ghost and the
 * rubber band, and **run** has what the run has painted over the drawing,
 * which arrives as data in `live` and is worked out in `model/panel.ts`.
 *
 * What a press means is neither mode's business here. The view hands over a
 * gesture machine (model/machine.ts) — the editor's `Gesture`, the run view's
 * `Drag` — and this converts pixels into squares, feeds it one call per event,
 * and maps each outcome onto rendering and events. It holds a pointer position
 * for the wireline and the ghost, and none of it survives the gesture.
 */

import { LitElement, html, svg, nothing, type SVGTemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import {
  emptyDrawing,
  symbolOf,
  wireKey,
  wirePins,
  type Drawing,
  type PinRef,
  type SymbolSpec,
  type Wire,
} from "../model/drawing.js";
import type { Editor } from "../model/editor.js";
import { GESTURING, TRANSIENT, svgFile } from "../model/export.js";
import {
  centreOf,
  facePoint,
  gridPointOf,
  labelAnchor,
  labelTurn,
  placed,
  transformOf,
  type Point,
} from "../model/geometry.js";
import {
  chosenWay,
  dark,
  lit,
  litLast,
  litWires,
  unpaired,
  type Chosen,
} from "../model/inspect.js";
import type { Machine, Outcome } from "../model/machine.js";
import type { Aspect, Marker, Overlay } from "../model/panel.js";
import { anchorAt, arrowPose, fitBox, type Box } from "../model/scene.js";
import { UNREVIEWED, type Review } from "../model/store.js";
import { pointOf, under, type Under } from "../model/under.js";
import { artwork, DEFS } from "../render/artwork.js";
import { BLOCK, FACE, PIN, PORTAL, RING, fitted } from "../render/units.js";
import { canvasStyles, exportStyles } from "./tc-canvas.styles.js";

/** Which of the two surfaces this is. */
export type Mode = "edit" | "run";

/**
 * What the canvas lights, worked out once a render: the legs of the symbols on
 * a way, and the classes each lit wire carries.
 *
 * Both modes light a way, and one rule emits it. The editor lights the transit
 * chosen in the netlist pane, or the way a refusal is about, in the red that
 * means derivation stopped (ADR-0024); the run view lights a committed route
 * in the two colours the dispatcher's claim on it reads in (ui/PANEL.md).
 */
interface Lighting {
  legs: Map<string, Set<string>>;
  /** Wire, as `wireKey` names it → the classes it wears beyond `wire`. A wire
   *  that is not lit is absent. */
  wires: Map<string, string>;
  /** Whether the way is one a refusal is about rather than one chosen. */
  refused: boolean;
}

@customElement("tc-canvas")
export class TcCanvas extends LitElement {
  static override styles = canvasStyles;

  /** Which surface this is. Reflected, so the stylesheet can say what only one
   *  of the two wears without a class the template has to remember. */
  @property({ reflect: true }) mode: Mode = "edit";

  /** The document painted, in run mode. Edit mode has an `editor` and the
   *  document is that session's, so there is one of it either way. */
  @property({ attribute: false }) drawing: Drawing = emptyDrawing("untitled");

  /** The editing session over the document, which only edit mode has. A run
   *  view hands over none, and nothing that only editing draws is on the
   *  sheet. */
  @property({ attribute: false }) editor: Editor | null = null;

  /** What the store says the drawing means, `null` before it has been asked. */
  @property({ attribute: false }) review: Review | null = null;

  /** The transit whose way is lit, chosen in the netlist pane. */
  @property({ attribute: false }) chosen: Chosen | null = null;

  /** What a run has painted over the drawing, which only run mode has. Data
   *  and nothing else: occupancy, aspects, markers, the lit route, point
   *  positions and a train between two blocks all arrive worked out. */
  @property({ attribute: false }) live: Overlay | null = null;

  /** What a press means, which is the view's and never this component's. */
  @property({ attribute: false }) machine!: Machine;

  @state() private view: Box = { x: -1, y: -1, w: 16, h: 11 };
  @state() private pointer: Point | null = null;
  /** Where the middle button was pressed, while it is down. The anchor stays
   *  put: the view moves under the pointer, so the same screen position reads
   *  as the anchor again on the next event. */
  private panning: Point | null = null;

  private watch = new ResizeObserver(() => this.square());

  override connectedCallback(): void {
    super.connectedCallback();
    this.watch.observe(this);
  }

  override disconnectedCallback(): void {
    this.watch.disconnect();
    super.disconnectedCallback();
  }

  /** The editing session, where the mode has one: the one place `mode` and
   *  `editor` are tied together, so no drawing method has to check both. */
  private get editing(): Editor | null {
    return this.mode === "edit" ? this.editor : null;
  }

  /** What the run has painted, where the mode has a run. */
  private get running(): Overlay | null {
    return this.mode === "run" ? this.live : null;
  }

  /** The document on the sheet: the editing session's where there is one, and
   *  the one handed over otherwise. Asked here rather than read off two
   *  properties that would then have to agree. */
  private get document(): Drawing {
    return this.editing?.drawing ?? this.drawing;
  }

  override render() {
    const { x, y, w, h } = this.view;
    const lighting = this.lighting();
    return html`
      <svg
        viewBox=${`${x} ${y} ${w} ${h}`}
        @pointerdown=${this.down}
        @pointermove=${this.moved}
        @pointerup=${this.up}
        @pointerleave=${this.left}
        @pointercancel=${this.left}
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
        ${this.faces()} ${this.wires(lighting)} ${this.symbols(lighting)}
        ${this.pins()} ${this.stacked()} ${this.arrows()} ${this.crossings()}
        ${this.disputes()} ${this.markers()} ${this.wireline()} ${this.reach()}
        ${this.rubberBand()} ${this.ghost()}
      </svg>
    `;
  }

  // --- the viewport -------------------------------------------------------

  /** Fit the whole drawing, with a margin. Placement is the document's, so
   *  there is nothing to lay out — only somewhere to look. The frame is
   *  `fitBox`, which is also what an export is drawn in, so a view fitted and
   *  a file written frame the same thing. */
  fit(): void {
    const pane = this.getBoundingClientRect();
    const shape = pane.width > 0 ? pane.height / pane.width : 0.7;
    const frame = fitBox(this.document, this.marks());
    const w = Math.max(frame.w, frame.h / shape);
    const h = w * shape;
    this.view = {
      x: frame.x - (w - frame.w) / 2,
      y: frame.y - (h - frame.h) / 2,
      w,
      h,
    };
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

  /** Where the labels of the portals pairing with nothing are drawn, which
   *  `fit` has to keep on screen. A portal's one pin is on the side away from
   *  its mouth, so the outermost thing in the drawing can be the very mark that
   *  wants looking at, a whole square outside the pin the margin is measured
   *  from. */
  private marks(): Point[] {
    return [...unpaired(this.review ?? UNREVIEWED).keys()].flatMap((name) => {
      const spec = this.document.symbols[name];
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
    const box = fitBox(this.document, this.marks());
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
    // `classList.remove` above rewrites only the attributes it touched, and
    // Lit writes the rest as its template composed them. Every class is
    // written back as its tokens so the same drawing gives the same bytes
    // whichever nodes a gesture happened to be on.
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

  // --- what both modes draw -----------------------------------------------

  /**
   * The way lit on the drawing, as the legs of the symbols it crosses and the
   * classes the wires under it wear.
   *
   * In edit mode it is the transit chosen in the netlist pane, or the way a
   * refusal is about. Naming the frog that makes two transits exclusive is a
   * claim about the drawing, and this is where it is checked by looking; a
   * refusal is the same kind of claim, so it lights the same way, in the red
   * that means derivation stopped (ADR-0024). The two never arrive together: a
   * drawing that refuses has no netlist to choose from.
   *
   * In run mode it is the committed route, already walked and already coloured
   * by the panel model — the same claim, made by the dispatcher instead of the
   * pointer.
   */
  private lighting(): Lighting {
    const live = this.running;
    if (live !== null) {
      return {
        legs: live.lit.legs,
        wires: new Map(
          [...live.lit.wires].map(([key, held]) => [key, `lit ${held}`]),
        ),
        refused: false,
      };
    }
    const review = this.review ?? UNREVIEWED;
    const refused = review.offending.length > 0;
    const ways = refused ? review.offending : chosenWay(review, this.chosen);
    // A wire sits outside every symbol's group, so a refusal is marked on the
    // line itself rather than inherited from one.
    const marked = refused ? "lit offending" : "lit";
    return {
      legs: lit(ways),
      wires: new Map(
        [...litWires(ways, this.document.wires)].map((key) => [key, marked]),
      ),
      refused,
    };
  }

  /** Every wire, in the order `inspect.litLast` puts them in, so a crossing
   *  unlit one cannot half hide a lit one. */
  private wires(lighting: Lighting): unknown {
    const alight = (wire: Wire) => lighting.wires.has(wireKey(wire));
    return litLast(this.document.wires, alight).map((wire) => {
      const [a, b] = wirePins(wire);
      const from = this.point(a);
      const to = this.point(b);
      if (from === null || to === null) return nothing;
      const worn = lighting.wires.get(wireKey(wire));
      return svg`<line class=${worn === undefined ? "wire" : `wire ${worn}`}
                       x1=${from.x} y1=${from.y} x2=${to.x} y2=${to.y} />`;
    });
  }

  private symbols(lighting: Lighting): unknown {
    const review = this.review ?? UNREVIEWED;
    const live = this.running;
    const blind = dark(review);
    const lone = unpaired(review);
    const unset = new Set(this.editing?.unaddressed() ?? []);
    // Asked once rather than per symbol: the machine works its marks out
    // afresh on every read, and a drop names one block.
    const target = this.machine.marks?.target?.block;
    return Object.entries(this.document.symbols).map(([name, spec]) => {
      const shifted = this.shift(name);
      return svg`
        <g
          class=${this.worn(name, lighting, target)}
          data-symbol=${name}
          transform=${`translate(${shifted.x} ${shifted.y})`}
        >
          <g transform=${transformOf(spec)}>
            ${artwork(
              spec,
              lighting.legs.get(name),
              blind.get(name),
              this.showing(name),
              live?.positions.get(name),
            )}
          </g>
          ${this.label(name, spec, lone.get(name))}
          ${unset.has(name) ? this.unaddressed(spec) : nothing}
        </g>
      `;
    });
  }

  /**
   * What a symbol's group wears beyond `symbol`.
   *
   * Edit mode marks what is selected and what a refusal is about. Run mode
   * marks how strong a claim the run has on it: a block wears its own state
   * and a junction symbol the strongest claim any transit through it carries,
   * and a block being on no transit's way, the two never meet on one symbol.
   * Occupancy outranks both, which is what reading the block's state first
   * says (ui/PANEL.md).
   */
  private worn(
    name: string,
    lighting: Lighting,
    target: string | undefined,
  ): string {
    const live = this.running;
    const marked =
      live === null
        ? [
            this.editing?.selection.has(name) === true ? "selected" : "",
            lighting.refused && lighting.legs.has(name) ? "offending" : "",
          ]
        : [
            live.blocks.get(name)?.state ?? live.lit.state.get(name) ?? "",
            live.blocks.get(name)?.dispute === undefined ? "" : "disputed",
            name === target ? "target" : "",
          ];
    return ["symbol", ...marked]
      .filter((one) => one !== "" && one !== "free")
      .join(" ");
  }

  /** The aspects a block's two signals show, keyed by end letter, which is what
   *  the artwork puts on each signal's group. An end the dispatcher never named
   *  simply has no aspect, and edit mode names none at all. */
  private showing(name: string): ReadonlyMap<string, Aspect> | undefined {
    const live = this.running;
    if (live === null) return undefined;
    return new Map(
      (["A", "B"] as const).flatMap((end) => {
        const shown = live.aspects.get(`${name}.${end}`);
        return shown === undefined ? [] : [[end, shown] as const];
      }),
    );
  }

  /**
   * The mark a turnout or a slip with no address wears: a ring round the
   * squares it covers, in the quieter of the two weights (ADR-0024).
   *
   * Such a drawing derives and cannot be driven, which is what the quiet
   * weight says and why the band stays clean. A ring rather than a wash over
   * the squares: that mark is already an overlap's, and a wash would cover the
   * artwork the ring is about. It sits in the symbol's own group, so it moves
   * with a drag as the label does.
   *
   * Which symbols wear one is `Editor.unaddressed`, read off the open drawing:
   * no review is asked, so the mark clears as soon as the drawing has the
   * address, which is when the properties dialog applies its draft.
   */
  private unaddressed(spec: SymbolSpec): unknown {
    const [c, r] = spec.at ?? [0, 0];
    const { w, h } = placed(spec).footprint;
    return svg`<rect class="unaddressed"
      x=${c + RING.inset} y=${r + RING.inset}
      width=${w - 2 * RING.inset} height=${h - 2 * RING.inset}
      rx=${RING.radius} />`;
  }

  /**
   * The text a symbol carries: a block's name or, on a run, the train standing
   * in it, and the label of a portal that pairs with nothing.
   *
   * A block's label is the only text a *correct* drawing carries
   * (EDITOR.md#symbol-geometry) — every other name is read in the properties
   * dialog and in the netlist pane, portals included. The unpaired portal's
   * label is a fault mark rather than a name the symbol wears: it is drawn in
   * red and it goes away when the label pairs.
   *
   * On a run the name is the train's when one stands there and the block's own
   * dimly otherwise, a train's name being the thing worth reading. A train's
   * name is the longer of the two, so this is where the fit usually does work.
   */
  private label(
    name: string,
    spec: SymbolSpec,
    lone: string | undefined,
  ): unknown {
    if (spec.kind === "portal") return this.portalLabel(spec, lone);
    if (spec.kind !== "block") return nothing;
    const live = this.running;
    const view = live?.blocks.get(name);
    const train = view?.state === "occupied" ? view.train : undefined;
    const worn =
      train !== undefined ? "name train" : live === null ? "name" : "name dim";
    return this.blockName(train ?? name, worn, spec);
  }

  /**
   * A block's label, centred in its rectangle and turned outside the artwork's
   * own group: upright on a horizontal block and read bottom to top on a
   * vertical one (`labelTurn`).
   *
   * The label turns with the block, so the rectangle's long side is the width
   * it has to fit whichever way the block stands.
   */
  private blockName(text: string, worn: string, spec: SymbolSpec): unknown {
    const { x, y } = centreOf(spec);
    return svg`<text class=${worn} x=${x} y=${y}
      font-size=${fitted(text, BLOCK.body.w)}
      transform=${`rotate(${labelTurn(spec)} ${x} ${y})`}>${text}</text>`;
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

  // --- what only the editor draws -----------------------------------------

  /**
   * Where a wire can land, drawn only while one is in flight.
   *
   * A dot sits on every face centre, which is every point `faceAt` can return
   * and every point a pin occupies, so the marks and the landing sites are the
   * same set. They answer a question that is only asked between the click that
   * starts a wire and the one that ends it, so the sheet is bare otherwise.
   */
  private faces(): unknown {
    if ((this.editing?.pendingFrom ?? null) === null) return nothing;
    const { x, y, w, h } = this.view;
    return svg`<rect class="faces" x=${x} y=${y} width=${w} height=${h}
                     fill="url(#faces)" />`;
  }

  /** Every pin, green where `/review` is satisfied with it and red where it is
   *  not. The front end computes no topology, so which are red is the store's
   *  answer and not this component's. */
  private pins(): unknown {
    const editor = this.editing;
    if (editor === null) return nothing;
    const red = new Set(this.review?.red_pins ?? []);
    return editor.allPins().map(({ pin, x, y }) => {
      const shifted = this.shift(symbolOf(pin));
      const worn = ["pin", red.has(pin) ? "red" : ""];
      if (editor.pendingFrom === pin) worn.push("pending");
      return svg`<circle
        class=${worn.filter((one) => one !== "").join(" ")}
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
    return (this.editing?.overlaps() ?? []).map(
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
    const from = this.editing?.pendingFrom ?? null;
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
    const editor = this.editing;
    const pending = editor?.pending ?? null;
    if (editor === null || pending === null || this.pointer === null) {
      return nothing;
    }
    const landing = editor.placementAt(this.pointer.x, this.pointer.y);
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
    const band = this.machine.marks?.band;
    if (band === undefined) return nothing;
    const { from, to } = band;
    return svg`<rect class="band"
      x=${Math.min(from.x, to.x)} y=${Math.min(from.y, to.y)}
      width=${Math.abs(to.x - from.x)} height=${Math.abs(to.y - from.y)} />`;
  }

  // --- what only a run draws ----------------------------------------------

  /** The direction arrow: on the track, ahead of the block's centre, pointing
   *  at the end the train faces. Unknown until the scheduler has said. */
  private arrows(): unknown {
    return [...(this.running?.blocks ?? [])].map(([name, view]) => {
      const spec = this.document.symbols[name];
      if (spec === undefined || view.toward === undefined) return nothing;
      const { x, y, angle } = arrowPose(spec, view.toward);
      return svg`<path class="arrow" d="M0.28 0 L-0.14 0.17 L-0.14 -0.17 Z"
        transform=${`translate(${x} ${y}) rotate(${angle})`} />`;
    });
  }

  /** A train the picture says is between two blocks: its name on the
   *  connection it is crossing, midway between the two block ends that transit
   *  joins, and in no block (ui/PANEL.md, #154). No arrow — the block it faces
   *  out of is one it has left. */
  private crossings(): unknown {
    return (this.running?.crossings ?? []).map(({ train, between }) => {
      const from = anchorAt(this.document, between[0]);
      const to = anchorAt(this.document, between[1]);
      if (from === null || to === null) return nothing;
      return svg`<text class="name train crossing"
        x=${(from.x + to.x) / 2} y=${(from.y + to.y) / 2}
        font-size=${fitted(train, BLOCK.body.w)}>${train}</text>`;
    });
  }

  /** What the detectors dispute, in words under the block it is about: the
   *  reading that contradicts the picture, since the picture itself is already
   *  on screen (#153). These are where a person is sent first, so they say
   *  which of the two contradictions this is rather than only that something is
   *  wrong. */
  private disputes(): unknown {
    return [...(this.running?.blocks ?? [])].map(([name, view]) => {
      const spec = this.document.symbols[name];
      if (spec === undefined || view.dispute === undefined) return nothing;
      const { x, y } = centreOf(spec);
      return svg`<text class="note disputed" x=${x} y=${y + 1}>
        reads ${view.dispute}
      </text>`;
    });
  }

  /** Request endpoints, ring by ring, with the reasons the model worded. */
  private markers(): unknown {
    return (this.running?.markers ?? []).map((marker) => this.marked(marker));
  }

  private marked(marker: Marker): unknown {
    const at = anchorAt(this.document, marker.at);
    if (at === null) return nothing;
    const { x, y } = at;
    return svg`
      <circle class=${`marker ${marker.role}`} cx=${x} cy=${y} r="0.3" />
      ${
        marker.note === undefined
          ? nothing
          : svg`<text class=${`note ${marker.role}`} x=${x} y=${y + 0.7}>
              ${marker.note}
            </text>`
      }
    `;
  }

  /** The drag in flight: a line from where the train was taken hold of, and a
   *  ring at each arrival end a drop here would ask for — so the gesture's
   *  meaning is on screen before the release (ui/PANEL.md). Both are the
   *  machine's answer, never a guess about feasibility. */
  private reach(): unknown {
    const marks = this.machine.marks;
    if (marks?.reach === undefined) return nothing;
    const { from, to } = marks.reach;
    return svg`
      <line class="reach" x1=${from.x} y1=${from.y} x2=${to.x} y2=${to.y} />
      ${(marks.target?.ends ?? []).map(
        (at) => svg`<circle class="marker hover" cx=${at.x} cy=${at.y} r="0.34" />`,
      )}
    `;
  }

  // --- gestures -----------------------------------------------------------

  /** What the machine said back, mapped onto rendering and events. After any
   *  outcome that drew something, a wire in progress wants the pointer: the
   *  wireline starts at the press before the first move arrives. */
  private apply(outcome: Outcome, point: Point): void {
    if (outcome === "quiet") return;
    if ((this.editing?.pendingFrom ?? null) !== null) this.pointer = point;
    if (outcome === "picked") this.picked();
    else if (outcome === "changed") this.changed();
    else this.requestUpdate();
  }

  private down(event: PointerEvent): void {
    const point = this.squareAt(event);
    // On the sheet rather than on whatever node is under the pointer: run mode
    // redraws on every frame off the bus, and a symbol whose markup changed
    // shape mid-drag would take the capture with it.
    (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
    if (event.button === 1) {
      this.panning = point;
      return;
    }
    this.apply(
      this.machine.down(point, {
        button: event.button,
        shift: event.shiftKey,
        screen: { x: event.clientX, y: event.clientY },
      }),
      point,
    );
  }

  private moved(event: PointerEvent): void {
    const point = this.squareAt(event);
    if (this.panning !== null) {
      this.view = {
        ...this.view,
        x: this.view.x + this.panning.x - point.x,
        y: this.view.y + this.panning.y - point.y,
      };
      return;
    }
    // Only the wireline and the ghost read the pointer, and `pointer` is state:
    // assigning it on every move would re-render the whole sheet to draw
    // nothing.
    const editor = this.editing;
    if (editor !== null && (editor.pendingFrom !== null || editor.pending !== null)) {
      this.pointer = point;
    }
    this.apply(
      this.machine.moved(point, { x: event.clientX, y: event.clientY }),
      point,
    );
  }

  private up(event: PointerEvent): void {
    const point = this.squareAt(event);
    this.panning = null;
    this.apply(
      this.machine.up(point, { x: event.clientX, y: event.clientY }),
      point,
    );
  }

  /** The pointer left the sheet, or the gesture under it was cancelled. */
  private left(): void {
    this.pointer = null;
    this.panning = null;
    if (this.machine.left() !== "quiet") this.requestUpdate();
  }

  /**
   * The right-click, told what was clicked: the machine's ruling, passed on to
   * the view with where the pointer was. What is in it is the machine's — the
   * symbol and the joint in the editor, the train standing there on a run —
   * and a null `found` opens no menu.
   */
  private menu(event: MouseEvent): void {
    event.preventDefault();
    const point = this.squareAt(event);
    const { outcome, found } = this.machine.menu(point);
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
    const point = this.squareAt(event);
    const scale = Math.exp(event.deltaY / 400);
    this.view = {
      x: point.x - (point.x - this.view.x) * scale,
      y: point.y - (point.y - this.view.y) * scale,
      w: this.view.w * scale,
      h: this.view.h * scale,
    };
  }

  // --- reading the drawing under the pointer ------------------------------

  /**
   * The grid point a client pixel position falls on, `null` where the sheet
   * has no transform yet.
   *
   * Public because a drag that began somewhere else ends here: a row dragged
   * out of the roster pane is let go over this surface, and where a pixel
   * lands on the drawing is the surface's answer and nobody else's (#170).
   */
  gridAt(x: number, y: number): Point | null {
    const matrix = this.renderRoot.querySelector("svg")?.getScreenCTM() ?? null;
    if (matrix === null) return null;
    const grid = new DOMPoint(x, y).matrixTransform(matrix.inverse());
    return { x: grid.x, y: grid.y };
  }

  /** Where a pointer event is on the drawing, which is what every gesture
   *  call is given. */
  private squareAt(event: MouseEvent): Point {
    return this.gridAt(event.clientX, event.clientY) ?? { x: 0, y: 0 };
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
    return under(this.document, this.review ?? UNREVIEWED, point, (name) =>
      this.shift(name),
    );
  }

  /** Where a pin is drawn, which is where a wire has to end. */
  private point(pin: PinRef): Point | null {
    return pointOf(this.document, pin, (name) => this.shift(name));
  }

  /** How far a symbol is drawn from where the document puts it, which the
   *  machine knows: nothing except while a drag of the selection is in
   *  progress. */
  private shift(name: string): Point {
    return this.machine.shift(name);
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
