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
 * **It draws none of it.** `tc-canvas` in run mode is the surface, the same one
 * the editor draws on, so the viewport, the wires, the symbols and the labels
 * are written once and this view has zoom, pan and fit for free
 * ([#168](https://github.com/rails49/control/issues/168)). What this holds is
 * what only a run has: the session, the model the bus feeds, the overlay it
 * hands the canvas, and the machine that says what a drag means
 * (model/drag.ts).
 *
 * Everything shown is the panel model's answer (model/panel.ts). It computes
 * nothing: occupancy, aspects, markers, the lit route, arrival ends and
 * whether a train is busy all arrive as data.
 *
 * Its one source is the bus (ADR-0038). Reading a recorded trace was how this
 * view was built before `tc49 live` existed; a trace is the harness's now, and
 * a session is the only thing that feeds a picture.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/select/select.js";
import "@shoelace-style/shoelace/dist/components/option/option.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import {
  Drag,
  schedulingMachine,
  type Drop,
  type Painted,
} from "../model/drag.js";
import type { Drawing } from "../model/drawing.js";
import { outstanding, Panel, type Overlay } from "../model/panel.js";
import { positionsBySymbol } from "../model/scene.js";
import {
  listScenarios,
  readScenario,
  UNREVIEWED,
  type Review,
} from "../model/store.js";
import {
  gesture,
  Live,
  reversal,
  wanted,
  type Power,
  type Run,
} from "../model/trace.js";
import { panelStyles } from "./tc-panel.styles.js";
import "./tc-canvas.js";
import "./tc-menu.js";
import type { TcCanvas } from "./tc-canvas.js";
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
  /** How the run stands, `null` while no session is joined or before the
   *  dispatcher has said (ADR-0037). It is what the bar's HOLD/GO reads. */
  run: Run | null;
  /** Whether a train may move at all, `null` while no session is joined or
   *  before the layout has said (ADR-0041). The band says which it is, and
   *  the bar's GO is greyed while it is anything but `on`. */
  power: Power | null;
  /** What a session refused, or the store not answering. Never a fault of the
   *  drawing itself: those are marked where they are (ADR-0024). */
  trouble: string | null;
}

/** What the right-click found, as the canvas hands it over: `trainAt`'s answer
 *  with the pointer's position on it (model/drag.ts). It is also what the open
 *  menu is, there being nothing else to remember about one. */
interface Clicked {
  x: number;
  y: number;
  block: string;
  train: string;
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
  /** What was still disputed at the moment the hold was released, in words,
   *  `null` while there is nothing to say. */
  @state() private released: string | null = null;
  /** Bumped after each step: the model mutates in place, so rendering is
   *  asked for rather than observed. */
  @state() private beat = 0;
  /** The open right-click menu: where it hangs, and the block and train it
   *  is about, `null` for none. */
  @state() private menu: Clicked | null = null;

  private panel: Panel | null = null;
  /** Whether the run was running when the last frame was applied, which is
   *  what says a fresh hold has begun. */
  private wasRunning = false;
  /** The railroad the model was built for, so it is rebuilt when the app loads
   *  another and kept when anything else changes. */
  private built: string | null = null;
  /** Whether the canvas wants fitting once it has drawn: a railroad arrives
   *  here by joining a session as well as by the band's picker, and either way
   *  there is nowhere else the viewport should be looking. */
  private fitting = false;
  private live: Live | null = null;
  private socket: WebSocket | null = null;
  private readonly drag = new Drag();
  /** What a press on the canvas means here (model/drag.ts), bound to what is
   *  on screen. It answers quiet while there is no session to submit to,
   *  which is the whole of the gate on gesturing. */
  private readonly machine = schedulingMachine(
    this.drag,
    () => this.painted,
    (drop) => this.submit(drop),
  );

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
    this.fitting = true;
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
    // A fresh hold is a fresh decision, so what the last release was told
    // about goes with it. The transition and not the value: the run is still
    // `held` between the press and the dispatcher's answer, and clearing on
    // the value would take the notice down before it was read.
    const running = this.panel.run === "running";
    if (this.wasRunning && !running) this.released = null;
    this.wasRunning = running;
    this.beat++;
  }

  /**
   * Hold the run, or release it: one `run_wanted` naming where it should
   * stand (ADR-0037). The app presses it on the bar, the socket is here, and
   * the dispatcher's answer comes back on `state/run` and redraws the button.
   *
   * Releasing with disputes outstanding is allowed — the person decides, not
   * the check — and the panel says what is still disputed at the moment of
   * release ([#153](https://github.com/rails49/control/issues/153)). It is a
   * notice beside the press and not a question: nothing is blocked, and the
   * amber marks the panel was carrying go with the hold, so this is the same
   * answer in words for as long as the run they were released into is
   * running.
   */
  press(run: Run): void {
    if (this.socket === null || this.panel === null) return;
    this.released = run === "running" ? outstanding(this.panel.disputes()) : null;
    this.socket.send(wanted(run));
  }

  private leave(): void {
    this.drag.cancel();
    this.menu = null;
    this.joining = null;
    this.released = null;
    this.wasRunning = false;
    this.socket?.close();
    this.socket = null;
    this.live = null;
    this.session = null;
    this.connected = false;
  }

  // --- scheduling by drag ---------------------------------------------------

  /** Whether a drag means anything: only a joined session has anywhere to
   *  gesture at, and only there does a train look like something to pick up. */
  private get scheduling(): boolean {
    return this.connected && this.drawing !== null && this.panel !== null;
  }

  /** What is on screen for a gesture to be about, `null` where nothing is.
   *  Read afresh on each call by the machine: the bus moves under a gesture in
   *  flight, and a session may go while one is. */
  private get painted(): Painted | null {
    const drawing = this.drawing;
    const model = this.panel;
    if (!this.scheduling || drawing === null || model === null) return null;
    return {
      drawing,
      review: this.review ?? UNREVIEWED,
      blocks: model.blocks(),
    };
  }

  /**
   * The drop: one `request_wanted`, filter-free (ui/PANEL.md). The gesture
   * names the train and where to put it, and the scheduler composes the
   * request — the id and the departure end are its (ADR-0036). The
   * dispatcher's answer comes back over the same socket and renders itself.
   *
   * The machine calls it, the canvas having driven the gesture: writing to the
   * bus is this view's and no model's.
   */
  private submit(drop: Drop): void {
    if (this.panel === null) return;
    this.socket?.send(gesture(this.panel.compose(drop.train, drop.dest)));
  }

  // --- turning a train around -----------------------------------------------

  /**
   * The right-click, as the canvas passes it on: the menu over the block a
   * train stands in, and nothing anywhere else (#124).
   *
   * Which train was clicked is `trainAt`'s answer, the same question the press
   * that takes hold of one asks (model/drag.ts), so the two can never
   * disagree. A press that had started a drag — a long press on a touch screen
   * raises `contextmenu` — has been abandoned by the machine, the menu taking
   * the gesture over.
   */
  private offer(event: CustomEvent<Clicked>): void {
    this.menu = event.detail;
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

  // --- painting -------------------------------------------------------------

  override render() {
    const drawing = this.drawing;
    const live = this.overlay;
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
        ${this.released === null
          ? nothing
          : html`<span class="released">${this.released}</span>`}
        <span class="spacer"></span>
        ${this.session === null
          ? nothing
          : html`<sl-button size="small" @click=${this.leave}>Leave</sl-button>`}
      </header>
      <main>
        ${drawing === null || live === null
          ? nothing
          : html`
              <tc-canvas
                mode="run"
                class=${this.scheduling ? "scheduling" : ""}
                .drawing=${drawing}
                .review=${this.review}
                .live=${live}
                .machine=${this.machine}
                @canvas-menu=${this.offer}
              ></tc-canvas>
            `}
      </main>

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
      run: this.session === null ? null : (this.panel?.run ?? null),
      power: this.session === null ? null : (this.panel?.power ?? null),
      trouble: this.trouble,
    };
  }

  /** The last status the app was told, so it is told again only when one of
   *  the four has moved. */
  private said: RunStatus | null = null;

  override updated(): void {
    if (this.fitting) {
      this.fitting = false;
      this.canvas?.fit();
    }
    const now = this.status;
    const was = this.said;
    if (
      was !== null &&
      was.joined === now.joined &&
      was.linked === now.linked &&
      was.boundary === now.boundary &&
      was.run === now.run &&
      was.power === now.power &&
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

  /**
   * What the run has painted over the drawing, for the canvas to draw (#168).
   *
   * Every entry is the panel model's own answer, worked out afresh on each
   * render because each is the last frame's. Point positions are the one thing
   * the model cannot answer alone: they are commanded by address, and the
   * drawing is what turns an address back into a symbol (ADR-0022,
   * ui/PANEL.md).
   */
  private get overlay(): Overlay | null {
    const model = this.panel;
    if (model === null || this.drawing === null) return null;
    return {
      blocks: model.blocks(),
      lit: model.lit(),
      aspects: model.aspects(),
      positions: positionsBySymbol(this.drawing, model.positionsByAddress()),
      crossings: model.crossings(),
      markers: model.markers(),
    };
  }

  // --- the viewport, which is the canvas's ----------------------------------

  /** Zoom and fit, pressed on the bar or typed on the keyboard. The app asks
   *  whichever view is current, and the surface is the same one the editor
   *  draws on. */
  zoom(scale: number): void {
    this.canvas?.zoom(scale);
  }

  fit(): void {
    this.canvas?.fit();
  }

  private get canvas(): TcCanvas | null {
    return this.renderRoot.querySelector<TcCanvas>("tc-canvas");
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-panel": TcPanel;
  }
}
