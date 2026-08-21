/**
 * The panel (ui/PANEL.md): the drawing with the railroad's state painted on
 * top, fed either by a recorded trace or by a live session over the bridge,
 * and — live — scheduling by drag and turning a train around by right-click.
 *
 * Everything shown is the panel model's answer (model/panel.ts) and everything
 * a drag means is the drag model's (model/drag.ts). This component loads the
 * documents, converts the pointer's pixels into squares, paints, and sends the
 * frames the relay accepts. It computes nothing: occupancy, aspects, markers,
 * lit legs, arrival ends and whether a train is busy all arrive as data.
 *
 * The two sources are exclusive: picking a railroad replays a trace, joining a
 * session runs live, and only a live session can gesture — a replay has nobody
 * to gesture at.
 */

import { LitElement, html, svg, nothing } from "lit";
import { customElement, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/select/select.js";
import "@shoelace-style/shoelace/dist/components/option/option.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import { Drag, trainAt } from "../model/drag.js";
import { dark } from "../model/inspect.js";
import { wirePins, type Drawing } from "../model/drawing.js";
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
  type Marker,
} from "../model/panel.js";
import { anchorAt, arrowPose, fitBox, positionsBySymbol } from "../model/scene.js";
import {
  listDrawings,
  listScenarios,
  readDrawing,
  readScenario,
  review,
  type Review,
} from "../model/store.js";
import { gesture, Live, parseTrace, Replay, reversal } from "../model/trace.js";
import type { Position } from "../symbols.generated.js";
import { pointOf } from "../model/under.js";
import { artwork, DEFS } from "../render/artwork.js";
import { BLOCK, fitted } from "../render/units.js";
import { panelStyles } from "./tc-panel.styles.js";
import "./tc-header.js";
import "./tc-menu.js";
import type { Mode } from "./tc-header.js";
import type { MenuItem } from "./tc-menu.js";

/** The one action the panel's menu offers, named once so the item and the
 *  handler cannot drift apart. */
const TURN_AROUND = "turn-around";

/** Where `tc49 live` puts the bridge. Overridable for a session somewhere
 *  else, which is the whole of the browser's configuration. */
const BRIDGE =
  new URLSearchParams(location.search).get("bridge") ??
  `ws://${location.hostname || "127.0.0.1"}:8766`;

@customElement("tc-panel")
export class TcPanel extends LitElement {
  static override styles = panelStyles;

  @state() private drawings: string[] = [];
  @state() private scenarios: string[] = [];
  @state() private drawing: Drawing | null = null;
  @state() private traceName: string | null = null;
  /** The scenario a live session was started from, `null` while replaying. */
  @state() private session: string | null = null;
  @state() private connected = false;
  @state() private playing = false;
  @state() private rate = 2; // boundaries per second
  @state() private trouble: string | null = null;
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
  private reviewed: Review | null = null;
  private replay: Replay | null = null;
  private live: Live | null = null;
  private socket: WebSocket | null = null;
  private timer: number | null = null;
  private readonly drag = new Drag();

  override connectedCallback(): void {
    super.connectedCallback();
    void this.start();
  }

  override disconnectedCallback(): void {
    this.pause();
    this.leave();
    super.disconnectedCallback();
  }

  private async start(): Promise<void> {
    try {
      [this.drawings, this.scenarios] = await Promise.all([
        listDrawings(),
        listScenarios(),
      ]);
    } catch {
      this.trouble = "the store is not answering — run `tc49 serve`";
    }
  }

  /**
   * Load a drawing and what it means. The panel needs the derived layout, so
   * a drawing the store refuses to derive is trouble, not a canvas.
   *
   * The railroad already on screen is kept rather than rebuilt. A model built
   * afresh would forget everything the bus has shown it, and only the next
   * picture would bring any of it back. Callers say what should be forgotten,
   * with `reset`.
   */
  private async load(name: string): Promise<boolean> {
    if (this.drawing?.drawing === name && this.panel !== null) return true;
    const drawing = await readDrawing(name);
    const reviewed = await review(drawing);
    if (reviewed.layout === null || reviewed.explain === null) {
      this.trouble = reviewed.refused ?? `'${name}' does not derive`;
      return false;
    }
    this.panel = new Panel(reviewed.layout, reviewed.explain);
    this.reviewed = reviewed;
    this.drawing = drawing;
    this.trouble = null;
    return true;
  }

  // --- replaying a trace ----------------------------------------------------

  private async pick(name: string): Promise<void> {
    this.pause();
    this.leave();
    try {
      if (!(await this.load(name))) return;
      this.panel!.reset();
      this.replay?.restart();
      this.beat++;
    } catch (error) {
      this.trouble = String(error instanceof Error ? error.message : error);
    }
  }

  private async opened(input: HTMLInputElement): Promise<void> {
    const file = input.files?.[0];
    if (file === undefined) return;
    this.pause();
    try {
      this.replay = new Replay(parseTrace(await file.text()));
      this.panel?.reset();
      this.traceName = file.name;
      this.trouble = null;
      this.beat++;
    } catch (error) {
      this.trouble = `${file.name}: ${error instanceof Error ? error.message : error}`;
    }
    input.value = "";
  }

  private step(): void {
    if (this.panel === null || this.replay === null) return;
    for (const event of this.replay.step()) this.panel.apply(event);
    if (this.replay.done) this.pause();
    this.beat++;
  }

  private play(): void {
    if (this.playing || this.replay === null) return;
    this.playing = true;
    this.timer = window.setInterval(() => this.step(), 1000 / this.rate);
  }

  private pause(): void {
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
    this.playing = false;
  }

  private restart(): void {
    this.pause();
    this.replay?.restart();
    this.panel?.reset();
    this.beat++;
  }

  private paced(rate: number): void {
    this.rate = rate;
    if (this.playing) {
      this.pause();
      this.play();
    }
  }

  // --- joining a live session -----------------------------------------------

  /**
   * Join the session running a scenario: its railroad, then the bridge.
   *
   * The scenario says one thing only — which drawing to render. Nothing
   * retained says which railroad a session runs, and a topic that did would
   * be the bridge describing the run (#67). Everything else comes off the
   * bus: placement, locks and live requests off the dispatcher's retained
   * picture, facing off the scheduler's (ADR-0032, ADR-0036), both written by
   * apps that are always running, so there is no cold start to seed.
   */
  private async join(id: string): Promise<void> {
    // Rejoining the session already on screen keeps what the bus has shown;
    // anything else starts from nothing, so a replay's state or another
    // scenario's is not mistaken for this railroad's.
    if (id === "") return; // the select clears itself on leaving
    const rejoining = this.session === id && this.panel !== null;
    this.pause();
    this.leave();
    this.replay = null;
    this.traceName = null;
    try {
      const scenario = await readScenario(id);
      if (!(await this.load(scenario.layout))) return;
      if (!rejoining) this.panel!.reset();
      this.session = id;
      this.listen();
      this.beat++;
    } catch (error) {
      this.trouble = String(error instanceof Error ? error.message : error);
    }
  }

  private listen(): void {
    this.live = new Live();
    const socket = new WebSocket(BRIDGE);
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
      this.trouble = `no session at ${BRIDGE} — run \`tc49 live ${this.session}\``;
    });
    this.socket = socket;
  }

  private heard(message: string): void {
    if (this.live === null || this.panel === null) return;
    const event = this.live.read(message);
    if (event === null) return;
    this.panel.apply(event);
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
      this.reviewed!,
      this.panel!.blocks(),
      this.gridAt(event),
    );
    if (!took) return;
    (event.target as Element).setPointerCapture?.(event.pointerId);
    this.beat++;
  }

  private moved(event: PointerEvent): void {
    if (this.drag.train === null) return;
    this.drag.moved(this.drawing!, this.reviewed!, this.gridAt(event));
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
    const drop = this.drag.up(this.drawing!, this.reviewed!, this.gridAt(event));
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
      this.reviewed!,
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
    const ready = this.panel !== null && this.replay !== null;
    return html`
      <tc-header
        .drawing=${this.drawing?.drawing ?? null}
        .mode=${this.mode}
        .trace=${this.traceName}
        .trouble=${this.trouble}
        .linked=${this.connected}
        .boundary=${this.stamp}
      ></tc-header>

      <header>
        <sl-select
          size="small"
          placeholder="railroad…"
          hoist
          .value=${this.session === null ? (this.drawing?.drawing ?? "") : ""}
          @sl-change=${(event: Event) =>
            this.pick((event.target as HTMLSelectElement).value)}
        >
          ${this.drawings.map(
            (name) => html`<sl-option value=${name}>${name}</sl-option>`,
          )}
        </sl-select>
        <sl-button
          size="small"
          @click=${() =>
            (this.renderRoot.querySelector("input[type=file]") as HTMLInputElement).click()}
        >
          Open trace…
        </sl-button>
        <input
          type="file"
          accept=".jsonl,application/jsonl,text/plain"
          hidden
          @change=${(event: Event) => this.opened(event.target as HTMLInputElement)}
        />
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
          ? this.transport(ready)
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

  /** Trace controls. A live session is paced by `tc49 live --period`, so there
   *  is nothing here to step or wind on. */
  private transport(ready: boolean) {
    return html`
      <sl-button size="small" ?disabled=${!ready} @click=${this.restart}>
        Restart
      </sl-button>
      <sl-button size="small" ?disabled=${!ready || this.playing} @click=${this.step}>
        Step
      </sl-button>
      <sl-button
        size="small"
        ?disabled=${!ready}
        @click=${() => (this.playing ? this.pause() : this.play())}
      >
        ${this.playing ? "Pause" : "Play"}
      </sl-button>
      <label class="rate">
        <input
          type="range"
          min="0.5"
          max="10"
          step="0.5"
          .value=${String(this.rate)}
          @input=${(event: Event) =>
            this.paced(Number((event.target as HTMLInputElement).value))}
        />
        ${this.rate}/s
      </label>
    `;
  }

  /** Which of the two exclusive sources is feeding the panel. A session wins
   *  because joining one drops the replay; with neither, the railroad on
   *  screen is a drawing nothing is running on. */
  private get mode(): Mode {
    if (this.session !== null) return "live";
    return this.replay === null ? "unjoined" : "replay";
  }

  /** How far the run has got, from whichever source is feeding it. */
  private get stamp(): number | null {
    return (
      (this.session === null ? this.replay?.boundary : this.live?.boundary) ?? null
    );
  }

  private canvas() {
    if (this.drawing === null || this.panel === null) return nothing;
    const { x, y, w, h } = fitBox(this.drawing);
    const blocks = this.panel.blocks();
    const lit = this.panel.litLegs();
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
        ${this.wires()} ${this.symbols(blocks, lit, aspects, positions)}
        ${this.labels(blocks)} ${this.arrows(blocks)} ${this.markers()}
        ${this.gesture()}
      </svg>
    `;
  }

  private wires() {
    const drawing = this.drawing!;
    return drawing.wires.map((wire) => {
      const [a, b] = wirePins(wire);
      const from = pointOf(drawing, a);
      const to = pointOf(drawing, b);
      if (from === null || to === null) return nothing;
      return svg`<line class="wire" x1=${from.x} y1=${from.y}
                       x2=${to.x} y2=${to.y} />`;
    });
  }

  private symbols(
    blocks: Map<string, BlockView>,
    lit: Map<string, Set<string>>,
    aspects: ReadonlyMap<string, Aspect>,
    positions: ReadonlyMap<string, Position>,
  ) {
    const target = this.drag.drop?.block;
    const blind = dark(this.reviewed!);
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
      const classes = ["symbol", block?.state ?? "", name === target ? "target" : ""]
        .filter((one) => one !== "" && one !== "free")
        .join(" ");
      return svg`
        <g class=${classes} transform=${transformOf(spec)}>
          ${artwork(spec, lit.get(name), blind.get(name), showing, positions.get(name))}
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
