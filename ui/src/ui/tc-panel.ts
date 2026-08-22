/**
 * The run view (ui/PANEL.md): the drawing with the railroad's state painted on
 * top, fed by a live session over the bridge, and scheduling by drag and
 * turning a train around by right-click.
 *
 * The railroad it is painting is not its own — the app holds it and hands over
 * the drawing and the review
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * A session is still named by a scenario, so joining one names a railroad too:
 * this asks the app for it and waits, rather than reading a second copy. Which
 * of the two happened last is what the app has loaded, until a run needs no
 * scenario at all (#171).
 *
 * Everything shown is the panel model's answer (model/panel.ts) and everything
 * a drag means is the drag model's (model/drag.ts). This component converts
 * the pointer's pixels into squares, paints, and sends the frames the relay
 * accepts. It computes nothing: occupancy, aspects, markers, the lit route,
 * arrival ends and whether a train is busy all arrive as data.
 *
 * Its one source is the bus (ADR-0038). Reading a recorded trace was how this
 * view was built before `tc49 live` existed; a trace is the harness's now, and
 * a session is the only thing that feeds a picture.
 */

import { LitElement, html, svg, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/select/select.js";
import "@shoelace-style/shoelace/dist/components/option/option.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import { Drag, trainAt } from "../model/drag.js";
import {
  wireKey,
  wirePins,
  type Drawing,
  type Wire,
} from "../model/drawing.js";
import { dark, litLast } from "../model/inspect.js";
import {
  centreOf,
  labelTurn,
  transformOf,
  type Point,
} from "../model/geometry.js";
import {
  Panel,
  type Aspect,
  type BlockView,
  type LitRoute,
  type Marker,
} from "../model/panel.js";
import { anchorAt, arrowPose, fitBox, positionsBySymbol } from "../model/scene.js";
import { listScenarios, readScenario, type Review } from "../model/store.js";
import { gesture, Live, reversal } from "../model/trace.js";
import type { Position } from "../symbols.generated.js";
import { pointOf } from "../model/under.js";
import { artwork, DEFS } from "../render/artwork.js";
import { BLOCK, fitted } from "../render/units.js";
import { panelStyles } from "./tc-panel.styles.js";
import "./tc-menu.js";
import type { MenuItem } from "./tc-menu.js";

/**
 * What the run view knows about the run that the band and the bar do not:
 * whether a session is joined and answering, how far it has got, and what it
 * refused. One event carries all of it, because they change together and the
 * app keeps one copy.
 */
export interface RunStatus {
  joined: boolean;
  linked: boolean;
  boundary: number | null;
  /** What a session refused, or the store not answering. Never a fault of the
   *  drawing itself: those are marked where they are (ADR-0024). */
  trouble: string | null;
}

/** The one action the panel's menu offers, named once so the item and the
 *  handler cannot drift apart. */
const TURN_AROUND = "turn-around";

/** Where `tc49 live` puts the bridge. Overridable for a session somewhere
 *  else, which is the whole of the browser's configuration — the railroad is
 *  not part of it, the panel naming that in the socket path (#148). */
const BRIDGE =
  new URLSearchParams(location.search).get("bridge") ??
  `ws://${location.hostname || "127.0.0.1"}:8766`;

@customElement("tc-panel")
export class TcPanel extends LitElement {
  static override styles = panelStyles;

  /** The loaded railroad, the app's own document. */
  @property({ attribute: false }) drawing: Drawing | null = null;

  /** What the store says that drawing means. A railroad that does not derive
   *  has no layout to paint on, and the band already says so. */
  @property({ attribute: false }) review: Review | null = null;

  @state() private scenarios: string[] = [];
  /** The scenario a live session was started from, `null` while none is. */
  @state() private session: string | null = null;
  @state() private connected = false;
  @state() private trouble: string | null = null;
  /** The scenario whose railroad has been asked for and not yet arrived. The
   *  socket is opened once it has: a frame heard before there is a model to
   *  apply it to would be a frame lost, and the drain a join opens with is the
   *  whole of the run's picture. */
  private joining: { id: string; railroad: string } | null = null;
  /** Bumped after each step: the model mutates in place, so rendering is
   *  asked for rather than observed. */
  @state() private beat = 0;
  /** The open right-click menu: where it hangs, and the block and train it
   *  is about, `null` for none. */
  @state() private menu: {
    x: number;
    y: number;
    block: string;
    train: string;
  } | null = null;

  private panel: Panel | null = null;
  /** The railroad the model was built for, so it is rebuilt when the app loads
   *  another and kept when anything else changes. */
  private built: string | null = null;
  private live: Live | null = null;
  private socket: WebSocket | null = null;
  private readonly drag = new Drag();

  override connectedCallback(): void {
    super.connectedCallback();
    void this.start();
  }

  override disconnectedCallback(): void {
    this.leave();
    super.disconnectedCallback();
  }

  private async start(): Promise<void> {
    try {
      this.scenarios = await listScenarios();
    } catch {
      this.trouble = "the store is not answering — run `tc49 serve`";
    }
  }

  /**
   * The app loaded a railroad, or reviewed the one that is loaded again.
   *
   * The model is built once per railroad and kept across everything else. One
   * built afresh would forget what the bus has shown it, and only the next
   * picture would bring any of it back. A railroad that does not derive has no
   * layout to build from, so nothing is painted and the band says why.
   */
  override willUpdate(changed: Map<string, unknown>): void {
    if (!changed.has("drawing") && !changed.has("review")) return;
    const name = this.drawing?.drawing ?? null;
    const layout = this.review?.layout ?? null;
    const explain = this.review?.explain ?? null;
    if (name === null || layout === null || explain === null) {
      if (name !== this.built) this.gone();
      return;
    }
    if (name === this.built) return;
    // A railroad swapped under a joined session would paint one railroad's
    // events on another's picture, which is what naming the session in the
    // socket path was for (#148).
    if (this.session !== null && this.joining?.railroad !== name) this.leave();
    this.panel = new Panel(layout, explain, this.drawing!.wires);
    this.built = name;
    this.beat++;
    this.finish();
  }

  /** The railroad went away, or stopped deriving. There is nothing to paint
   *  and nothing for a session to be a session of. */
  private gone(): void {
    this.leave();
    this.panel = null;
    this.built = null;
    this.beat++;
  }

  // --- joining a live session -----------------------------------------------

  /**
   * Join the session on a scenario: its railroad, then the bridge on the path
   * that names it.
   *
   * The view names the session (#148). The scenario says which railroad to
   * render *and* which railroad to be fed, those being one choice: a socket
   * opened without it would render one railroad on another's events. The
   * railroad is the app's to load, so it is asked for and the socket waits on
   * it; everything else comes off the bus — placement, locks and live requests
   * off the dispatcher's retained picture, facing off the scheduler's
   * (ADR-0032, ADR-0036), both written by apps that are always running, so
   * there is no cold start to seed.
   */
  private async join(id: string): Promise<void> {
    if (id === "") return; // the select clears itself on leaving
    // Rejoining the session already on screen keeps what the bus has shown;
    // anything else starts from nothing, so another scenario's state is not
    // mistaken for this railroad's.
    const rejoining = this.session === id && this.panel !== null;
    this.leave();
    try {
      const scenario = await readScenario(id);
      this.joining = { id, railroad: scenario.layout };
      if (!rejoining) this.panel?.reset();
      if (this.built === scenario.layout) {
        this.finish();
        return;
      }
      this.dispatchEvent(
        new CustomEvent<string>("railroad-wanted", {
          detail: scenario.layout,
          bubbles: true,
          composed: true,
        }),
      );
    } catch (error) {
      this.trouble = String(error instanceof Error ? error.message : error);
    }
  }

  /** The railroad the join was waiting on is on screen, so the socket may be
   *  opened. A join the app answered with another railroad — the question
   *  before unsaved edits was declined, or a picker press overtook it — never
   *  finishes, and the select is left showing nothing joined. */
  private finish(): void {
    const waiting = this.joining;
    if (waiting === null || waiting.railroad !== this.built) return;
    this.joining = null;
    this.session = waiting.id;
    this.listen();
    this.beat++;
  }

  /** Open the socket on the scenario's own path: the session runs the
   *  railroad named there, building it if it is running another, and
   *  switching is the `leave` and `listen` `join` already does. */
  private listen(): void {
    this.live = new Live();
    const at = `${BRIDGE}/${this.session}`;
    const socket = new WebSocket(at);
    socket.addEventListener("open", () => {
      this.connected = true;
      this.trouble = null;
    });
    socket.addEventListener("message", (frame) => this.heard(String(frame.data)));
    socket.addEventListener("close", () => {
      this.connected = false;
      this.menu = null; // nowhere left to send what it offers
    });
    socket.addEventListener("error", () => {
      this.trouble = `no session at ${at} — run \`tc49 live\``;
    });
    this.socket = socket;
  }

  private heard(message: string): void {
    if (this.live === null || this.panel === null) return;
    const heard = this.live.read(message);
    if (heard === null) return;
    // The session refusing something — a scenario it does not have, a frame
    // it will not relay — is shown rather than swallowed: it is the only
    // answer a gesture or a join ever gets when it goes wrong.
    if ("error" in heard) {
      this.trouble = heard.error;
      return;
    }
    this.panel.apply(heard.event);
    // An open menu is about one train in one block, and the run can end
    // both. It is taken down rather than hidden: a menu merely filtered out
    // of the render leaves nothing to dismiss and springs back the next time
    // that train stands there.
    const at = this.menu;
    if (at !== null && !this.panel.standsIn(at.train, at.block)) this.menu = null;
    this.beat++;
  }

  private leave(): void {
    this.drag.cancel();
    this.menu = null;
    this.joining = null;
    this.socket?.close();
    this.socket = null;
    this.live = null;
    this.session = null;
    this.connected = false;
  }

  // --- scheduling by drag ---------------------------------------------------

  /** Whether a drag means anything: only a joined session has anywhere to
   *  gesture at. */
  private get scheduling(): boolean {
    return this.connected && this.drawing !== null && this.panel !== null;
  }

  private down(event: PointerEvent): void {
    if (!this.scheduling) return;
    const took = this.drag.down(
      this.drawing!,
      this.review!,
      this.panel!.blocks(),
      this.gridAt(event),
    );
    if (!took) return;
    (event.target as Element).setPointerCapture?.(event.pointerId);
    this.beat++;
  }

  private moved(event: PointerEvent): void {
    if (this.drag.train === null) return;
    this.drag.moved(this.drawing!, this.review!, this.gridAt(event));
    this.beat++;
  }

  /**
   * The drop: one `request_wanted`, filter-free (ui/PANEL.md). The gesture
   * names the train and where to put it, and the scheduler composes the
   * request — the id and the departure end are its (ADR-0036). The
   * dispatcher's answer comes back over the same socket and renders itself.
   */
  private up(event: PointerEvent): void {
    if (this.drag.train === null) return;
    const drop = this.drag.up(this.drawing!, this.review!, this.gridAt(event));
    this.beat++;
    if (drop === null) return;
    this.socket?.send(gesture(this.panel!.compose(drop.train, drop.dest)));
  }

  private abandon(): void {
    if (this.drag.train === null) return;
    this.drag.cancel();
    this.beat++;
  }

  // --- turning a train around -----------------------------------------------

  /**
   * The right-click: the menu over the block a train stands in, and nothing
   * anywhere else (#124).
   *
   * The native menu is suppressed over the whole drawing, the way `tc-canvas`
   * suppresses it, so a right-click on paper is not half this gesture and
   * half the browser's. The press that opened this may have started a drag —
   * a long press on a touch screen raises `contextmenu` — and the menu takes
   * it over.
   */
  private offer(event: MouseEvent): void {
    event.preventDefault();
    this.abandon();
    this.menu = null;
    if (!this.scheduling) return;
    const standing = trainAt(
      this.drawing!,
      this.review!,
      this.panel!.blocks(),
      this.gridAt(event),
    );
    if (standing === null) return;
    this.menu = { x: event.clientX, y: event.clientY, ...standing };
  }

  /**
   * The one item the panel offers, greyed while that train has a request in
   * flight: the panel's only pre-judgement of a gesture, against the
   * filter-free drag where every drop submits (ui/PANEL.md). "Turn around"
   * and not "Reverse", which is the throttle's word, this moving nothing.
   *
   * Worked out afresh on every event, so the item ungreys the moment the
   * request is answered.
   */
  private get offered(): MenuItem[] {
    const at = this.menu;
    if (at === null || this.panel === null) return [];
    return [
      {
        label: "Turn around",
        action: TURN_AROUND,
        disabled: this.panel.inFlight(at.train),
      },
    ];
  }

  /** Chosen: one `reversal_wanted` naming the train. The scheduler flips its
   *  facing and the arrow follows, which is the whole of the feedback. The
   *  action is read rather than assumed, a throttle being the leaf this menu
   *  grows next (ui/PANEL.md). */
  private chose(event: CustomEvent<string>): void {
    const train = this.menu?.train;
    this.menu = null;
    if (train === undefined || event.detail !== TURN_AROUND) return;
    this.socket?.send(reversal(train));
  }

  private gridAt(event: MouseEvent): Point {
    const element = this.renderRoot.querySelector("svg")!;
    const matrix = element.getScreenCTM();
    if (matrix === null) return { x: 0, y: 0 };
    const point = element.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const grid = point.matrixTransform(matrix.inverse());
    return { x: grid.x, y: grid.y };
  }

  // --- painting -------------------------------------------------------------

  override render() {
    return html`
      <header>
        <sl-select
          size="small"
          placeholder="live session…"
          hoist
          .value=${this.session ?? ""}
          @sl-change=${(event: Event) =>
            this.join((event.target as HTMLSelectElement).value)}
        >
          ${this.scenarios.map(
            (name) => html`<sl-option value=${name}>${name}</sl-option>`,
          )}
        </sl-select>
        <span class="spacer"></span>
        ${this.session === null
          ? nothing
          : html`<sl-button size="small" @click=${this.leave}>Leave</sl-button>`}
      </header>
      <main>${this.canvas()}</main>

      <tc-menu
        .at=${this.menu}
        .items=${this.offered}
        @menu-action=${this.chose}
        @menu-dismissed=${() => {
          this.menu = null;
        }}
      ></tc-menu>
    `;
  }

  /** What the band and the bar read off the run, told rather than reached
   *  for: only this view knows any of it, and it changes as the bus moves. */
  private get status(): RunStatus {
    return {
      joined: this.session !== null,
      linked: this.connected,
      boundary: this.live?.boundary ?? null,
      trouble: this.trouble,
    };
  }

  /** The last status the app was told, so it is told again only when one of
   *  the four has moved. */
  private said: RunStatus | null = null;

  override updated(): void {
    const now = this.status;
    const was = this.said;
    if (
      was !== null &&
      was.joined === now.joined &&
      was.linked === now.linked &&
      was.boundary === now.boundary &&
      was.trouble === now.trouble
    ) {
      return;
    }
    this.said = now;
    this.dispatchEvent(
      new CustomEvent<RunStatus>("run-status", {
        detail: now,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private canvas() {
    if (this.drawing === null || this.panel === null) return nothing;
    const { x, y, w, h } = fitBox(this.drawing);
    const blocks = this.panel.blocks();
    const lit = this.panel.lit();
    const aspects = this.panel.aspects();
    // Where each point lies: the addresses the alignment command carried, read
    // back as the symbols wearing them (ui/PANEL.md).
    const positions = positionsBySymbol(
      this.drawing,
      this.panel.positionsByAddress(),
    );
    return svg`
      <svg
        viewBox=${`${x} ${y} ${w} ${h}`}
        class=${this.scheduling ? "scheduling" : ""}
        @pointerdown=${this.down}
        @pointermove=${this.moved}
        @pointerup=${this.up}
        @pointercancel=${this.abandon}
        @contextmenu=${this.offer}
      >
        <defs>${DEFS}</defs>
        <rect class="sheet" x=${x} y=${y} width=${w} height=${h} />
        ${this.wires(lit)} ${this.symbols(blocks, lit, aspects, positions)}
        ${this.labels(blocks)} ${this.arrows(blocks)} ${this.crossings()}
        ${this.disputes(blocks)} ${this.markers()}
        ${this.gesture()}
      </svg>
    `;
  }

  /** Every wire, in the order `inspect.litLast` puts them in, each lit one
   *  carrying the state of the transit it is on. */
  private wires(lit: LitRoute) {
    const drawing = this.drawing!;
    const alight = (wire: Wire) => lit.wires.has(wireKey(wire));
    return litLast(drawing.wires, alight).map((wire) => {
      const [a, b] = wirePins(wire);
      const from = pointOf(drawing, a);
      const to = pointOf(drawing, b);
      if (from === null || to === null) return nothing;
      // A wire sits outside every symbol's group, so the state rides on the
      // line itself rather than being inherited from one.
      const held = lit.wires.get(wireKey(wire));
      return svg`<line class=${held === undefined ? "wire" : `wire lit ${held}`}
                       x1=${from.x} y1=${from.y} x2=${to.x} y2=${to.y} />`;
    });
  }

  private symbols(
    blocks: Map<string, BlockView>,
    lit: LitRoute,
    aspects: ReadonlyMap<string, Aspect>,
    positions: ReadonlyMap<string, Position>,
  ) {
    const target = this.drag.drop?.block;
    const blind = dark(this.review!);
    return Object.entries(this.drawing!.symbols).map(([name, spec]) => {
      const block = blocks.get(name);
      // Keyed by end letter, which is what the artwork puts on each signal's
      // group; an end the dispatcher never named simply has no aspect.
      const showing = new Map(
        (["A", "B"] as const).flatMap((end) => {
          const shown = aspects.get(`${name}.${end}`);
          return shown === undefined ? [] : [[end, shown] as const];
        }),
      );
      // A block wears its own state and a junction symbol the strongest claim
      // any transit through it carries; a block is on no transit's way, so
      // the two never meet on one symbol. Occupancy outranks both all the
      // same, which is what reading the block's state first says.
      const state = block?.state ?? lit.state.get(name) ?? "";
      const classes = [
        "symbol",
        state,
        block?.dispute === undefined ? "" : "disputed",
        name === target ? "target" : "",
      ]
        .filter((one) => one !== "" && one !== "free")
        .join(" ");
      return svg`
        <g class=${classes} transform=${transformOf(spec)}>
          ${artwork(spec, lit.legs.get(name), blind.get(name), showing, positions.get(name))}
        </g>
      `;
    });
  }

  /** A block's text, turned with the block as the editor turns it: its train
   *  when one stands there, its own name dimly otherwise. A train's name is
   *  the longer of the two, so this is where the fit is usually doing work. */
  private labels(blocks: Map<string, BlockView>) {
    return Object.entries(this.drawing!.symbols).map(([name, spec]) => {
      if (spec.kind !== "block") return nothing;
      const view = blocks.get(name);
      const { x, y } = centreOf(spec);
      const occupied = view?.state === "occupied" && view.train !== undefined;
      const text = occupied ? view!.train! : name;
      return svg`<text class=${occupied ? "name train" : "name"} x=${x} y=${y}
        font-size=${fitted(text, BLOCK.body.w)}
        transform=${`rotate(${labelTurn(spec)} ${x} ${y})`}>${text}</text>`;
    });
  }

  /** What the detectors dispute, in words under the block it is about: the
   *  reading that contradicts the picture, since the picture itself is
   *  already on screen (#153). These are where a person is sent first, so
   *  they say which of the two contradictions this is rather than only that
   *  something is wrong. */
  private disputes(blocks: Map<string, BlockView>) {
    return [...blocks].map(([name, view]) => {
      const spec = this.drawing!.symbols[name];
      if (spec === undefined || view.dispute === undefined) return nothing;
      const { x, y } = centreOf(spec);
      return svg`<text class="note disputed" x=${x} y=${y + 1}>
        reads ${view.dispute}
      </text>`;
    });
  }

  /** A train the picture says is between two blocks: its name on the
   *  connection it is crossing, midway between the two block ends that
   *  transit joins, and in no block (ui/PANEL.md, #154). No arrow — the
   *  block it faces out of is one it has left. */
  private crossings() {
    return this.panel!.crossings().map(({ train, between }) => {
      const from = anchorAt(this.drawing!, between[0]);
      const to = anchorAt(this.drawing!, between[1]);
      if (from === null || to === null) return nothing;
      return svg`<text class="name train crossing"
        x=${(from.x + to.x) / 2} y=${(from.y + to.y) / 2}
        font-size=${fitted(train, BLOCK.body.w)}>${train}</text>`;
    });
  }

  /** The direction arrow: on the track, ahead of the block's centre, pointing
   *  at the end the train faces. Unknown until a granted move has said. */
  private arrows(blocks: Map<string, BlockView>) {
    return [...blocks].map(([name, view]) => {
      const spec = this.drawing!.symbols[name];
      if (spec === undefined || view.toward === undefined) return nothing;
      const { x, y, angle } = arrowPose(spec, view.toward);
      return svg`<path class="arrow" d="M0.28 0 L-0.14 0.17 L-0.14 -0.17 Z"
        transform=${`translate(${x} ${y}) rotate(${angle})`} />`;
    });
  }

  /** Request endpoints, ring by ring, with the reasons the model worded. */
  private markers() {
    return (this.panel?.markers() ?? []).map((marker) => this.marked(marker));
  }

  private marked(marker: Marker) {
    const at = anchorAt(this.drawing!, marker.at);
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

  /**
   * The drag in flight: a line from where the train was taken hold of, and a
   * ring at each arrival end a drop here would ask for — so the gesture's
   * meaning is on screen before the release (ui/PANEL.md).
   */
  private gesture() {
    const { from, to, drop } = this.drag;
    if (from === null || to === null) return nothing;
    return svg`
      <line class="reach" x1=${from.x} y1=${from.y} x2=${to.x} y2=${to.y} />
      ${(drop?.dest ?? []).map((end) => {
        const at = anchorAt(this.drawing!, end);
        return at === null
          ? nothing
          : svg`<circle class="marker hover" cx=${at.x} cy=${at.y} r="0.34" />`;
      })}
    `;
  }
}
