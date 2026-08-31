/**
 * The run view (ui/PANEL.md): the drawing with the railroad's state painted on
 * top, fed by a live session over the bridge, and scheduling by drag and
 * turning a train around by right-click.
 *
 * The railroad it is painting is not its own — the app holds it and hands over
 * the drawing and the review
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * **The loaded railroad is the session**: a run is built from a railroad and
 * nothing else ([#171](https://github.com/rails49/control/issues/171)), so the
 * band's picker is the only thing that sets which one, and this joins whatever
 * it has loaded. There is no session of its own to pick, and no way for the
 * two to name different railroads.
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
import "@shoelace-style/shoelace/dist/themes/light.css";

import {
  blockAt,
  Drag,
  schedulingMachine,
  type Drop,
  type Painted,
} from "../model/drag.js";
import type { Drawing } from "../model/drawing.js";
import type { Point } from "../model/geometry.js";
import {
  outstanding,
  Panel,
  roster,
  type Overlay,
  type Placed,
  type RosterRow,
} from "../model/panel.js";
import { positionsBySymbol } from "../model/scene.js";
import { readRoster, UNREVIEWED, type Review } from "../model/store.js";
import {
  gesture,
  Live,
  placement,
  reversal,
  runWanted,
  type Power,
  type Run,
} from "../model/trace.js";
import { panelStyles } from "./tc-panel.styles.js";
import "./tc-canvas.js";
import "./tc-menu.js";
import "./tc-roster.js";
import type { TcCanvas } from "./tc-canvas.js";
import type { MenuItem } from "./tc-menu.js";
import type { RosterDrag, TcRoster } from "./tc-roster.js";

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
  /** How many trains the run has on the layout. The bar reads it as the rule
   *  that trains on the layout freeze the drawing (`model/commands.ts`,
   *  ADR-0038): only this view knows, and the editing view is where it is
   *  felt. */
  placed: number;
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

/** Where the bridge is, as the page it is asked from says.
 *
 *  One path on the page's own origin, `/live`, which vite proxies in
 *  development and the reverse proxy strips in front of a layout server
 *  (docs/DEPLOY.md), so the URL the panel builds is the same either way. The
 *  scheme follows the page's: a plain `ws://` from a page served over TLS is
 *  mixed content and the browser refuses it, which is what a port of its own
 *  would have forced (ADR-0042).
 *
 *  `?bridge=` overrides it for a session somewhere else, and that is the
 *  whole of the browser's configuration — the railroad is not part of it, the
 *  panel naming that in the socket path (#148).
 */
export function bridgeAt(page: {
  protocol: string;
  host: string;
  search: string;
}): string {
  const named = new URLSearchParams(page.search).get("bridge");
  if (named !== null) return named;
  const scheme = page.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${page.host || "localhost:5173"}/live`;
}

const BRIDGE = bridgeAt(location);

/** How long the view waits before trying a dropped session again.
 *
 *  The loaded railroad **is** the session (#171), so a page with a railroad on
 *  it wants to be joined to that railroad and there is no choice left for a
 *  person to make: the band's picker says nothing about a name it is already
 *  showing, and a session that went is not a reason to make somebody reload.
 *  Three seconds is long enough not to hammer a port nothing is listening on,
 *  and short enough that restarting `tc49 live` under an open tab reconnects
 *  while the operator is still looking at it. */
export const RETRY_MS = 3000;

@customElement("tc-panel")
export class TcPanel extends LitElement {
  static override styles = panelStyles;

  /** The loaded railroad, the app's own document. */
  @property({ attribute: false }) drawing: Drawing | null = null;

  /** What the store says that drawing means. A railroad that does not derive
   *  has no layout to paint on, and the band already says so. */
  @property({ attribute: false }) review: Review | null = null;

  /** The railroad a live session is joined on, `null` while none is. It is
   *  the loaded railroad or nothing (#171). */
  @state() private session: string | null = null;
  @state() private connected = false;
  @state() private trouble: string | null = null;
  /** The railroad's roster: every train it owns and how long each is, read
   *  off the store when the session is joined (ADR-0039). The bus says where
   *  the trains are and never what there is to place. */
  @state() private stock: Record<string, { length: number }> = {};
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
   *  here when the band's picker loads one, and there is nowhere else the
   *  viewport should be looking. */
  private fitting = false;
  private live: Live | null = null;
  private socket: WebSocket | null = null;
  /** Joins started, so an overtaken one can tell that it has been. */
  private joins = 0;
  /** The retry waiting to be made, `null` while none is. */
  private waiting: ReturnType<typeof setTimeout> | null = null;
  private readonly drag = new Drag();
  /** What a press on the canvas means here (model/drag.ts), bound to what is
   *  on screen. It answers quiet while there is no session to submit to,
   *  which is the whole of the gate on gesturing. */
  private readonly machine = schedulingMachine(this.drag, {
    painted: () => this.painted,
    submit: (drop) => this.submit(drop),
    remove: (train) => this.lift(train),
    onRoster: (screen) => this.overRoster(screen),
  });

  override disconnectedCallback(): void {
    this.leave();
    super.disconnectedCallback();
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
    if (name === this.built) {
      // Loaded again with no session on it — the store was not answering when
      // it first arrived, or the session dropped this client — is how a page
      // gets back in, there being no picker of this view's own to re-press
      // (#171). The model is reused, so what the last session left in it that
      // no retained topic will replace goes first.
      if (this.session === null) {
        this.panel?.reset();
        void this.join(name);
      }
      return;
    }
    // A railroad swapped under a joined session would paint one railroad's
    // events on another's picture, which is what naming the session in the
    // socket path was for (#148).
    this.leave();
    this.panel = new Panel(layout, explain, this.drawing!.wires);
    this.built = name;
    this.fitting = true;
    this.beat++;
    void this.join(name);
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
   * Join the session on the railroad the app has loaded: its roster, then the
   * bridge on the path that names it.
   *
   * The railroad is the whole of the choice (#171): the socket path names it
   * and the session builds it, so what is rendered and what is fed can never
   * be two railroads. The roster is read here because it is the railroad's
   * asset and not the run's — what stock there is to place, which no topic
   * carries (ADR-0039). Everything else comes off the bus: placement, locks
   * and live requests off the dispatcher's retained picture, facing off the
   * scheduler's (ADR-0032, ADR-0036).
   *
   * **Only the latest join opens a socket.** The picker may be pressed
   * several times before a store answers, including back onto the railroad
   * already asked for, and an overtaken join that went on to `listen` would
   * leave a second socket open on the same run — every frame applied twice,
   * and its eventual close flipping a live session to disconnected. So each
   * join takes a number and drops itself if another has been started since;
   * `leave` takes one too, which is what abandons a join in flight.
   */
  private async join(railroad: string): Promise<void> {
    const mine = ++this.joins;
    try {
      const stock = await readRoster(railroad);
      if (mine !== this.joins || this.built !== railroad) return;
      this.stock = stock.trains;
      this.session = railroad;
      this.trouble = null;
      this.listen();
      this.beat++;
    } catch {
      // A roster read fails only when the store is not answering: a railroad
      // with no roster file is answered an empty one, and the drawing on
      // screen came from the same store a moment ago. So the message names
      // the fix rather than repeating what `fetch` said.
      this.trouble = "the store is not answering — run `tc49 serve`";
      if (mine === this.joins) this.retry();
    }
  }

  /** Try the loaded railroad again in a moment, unless a try is already
   *  waiting. What runs it is the same `join` the picker runs, so a session
   *  reached this way is a session reached any other way. */
  private retry(): void {
    if (this.waiting !== null) return;
    this.waiting = setTimeout(() => {
      this.waiting = null;
      if (this.built !== null && this.session === null) void this.join(this.built);
    }, RETRY_MS);
  }

  /** Open the socket on the railroad's own path: the session runs the
   *  railroad named there, building it if it is running another, and
   *  switching is the `leave` and `listen` `willUpdate` already does. */
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
      // Only for the socket still on screen: a swap closes the old one after
      // the new one is open, and that late close must not take the live
      // session down with it.
      if (socket !== this.socket) return;
      // The session has dropped this client — it switched railroads under one
      // operator, or the process went. What it was saying is no longer being
      // said, so the page holds no session at all: the roster empties, the
      // drawing thaws, and pressing the band's picker is what gets back in
      // (#171). Exactly what leaving one was, which is why it is that.
      this.leave();
      this.beat++;
      this.retry();
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
    // The session refusing something — a railroad it does not have, a frame
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
    // `connected` and not merely a socket: sending on a closed one is
    // discarded rather than thrown, and the notice below would then stand
    // for a release the dispatcher never heard.
    if (this.socket === null || !this.connected || this.panel === null) return;
    this.released = run === "running" ? outstanding(this.panel.disputes()) : null;
    this.socket.send(runWanted(run));
  }

  private leave(): void {
    this.joins++; // whatever join is in flight is not this railroad's
    if (this.waiting !== null) clearTimeout(this.waiting);
    this.waiting = null;
    this.drag.cancel();
    this.menu = null;
    this.stock = {};
    this.released = null;
    this.wasRunning = false;
    // Let go of it before closing it, so the `close` that follows is one this
    // no longer owns: the handler's own guard is what keeps a late close off
    // a live session, and it reads this field.
    const going = this.socket;
    this.socket = null;
    going?.close();
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

  // --- putting a train on the layout, and taking it off ---------------------
  //
  // The roster's two drags (ADR-0039). **The source decides what a drag
  // means**, never the run's state: a row picked up in the pane places its
  // train, a marker picked up on the canvas asks for a request, and one motion
  // cannot come to mean two things depending on a word in the band. Both of
  // these are refused while the run is running, which the pane says.

  /**
   * A row let go somewhere: one `placement_wanted` naming the block under the
   * pointer, or nothing where there is no block there.
   *
   * The pane says a row was dragged and where the pointer let go; what is
   * under it is the canvas's to answer, which is the same question the drag of
   * a marker asks (model/drag.ts). Letting go anywhere but on the sheet is how
   * a drag started by mistake is abandoned.
   *
   * That the release was **on the sheet** is asked of the element's own box,
   * not left to the transform: the drawing extends past the viewport and
   * `gridAt` reads any client point through the same matrix, so a point over
   * the pane maps onto whatever the pan has parked off-screen to the left. A
   * row let go over the pane would then place its train in a block nobody can
   * see.
   */
  private dropped(event: CustomEvent<RosterDrag>): void {
    const { train, x, y } = event.detail;
    const painted = this.painted;
    const at = this.onCanvas({ x, y }) ? (this.canvas?.gridAt(x, y) ?? null) : null;
    if (painted === null || at === null || this.panel?.run !== "held") return;
    const block = blockAt(painted.drawing, painted.review, at);
    if (block === null) return;
    this.socket?.send(placement(train, block));
  }

  /**
   * A marker dropped on the pane: the train comes off the layout, one
   * `placement_wanted` with no block.
   *
   * The dispatcher releases what it held and answers `train_removed`, and the
   * marker leaves the canvas because the picture no longer has the train —
   * this view retracts nothing of its own.
   */
  private lift(train: string): void {
    if (this.panel?.run !== "held") return;
    this.socket?.send(placement(train, null));
  }

  /** Whether a screen point is over the roster pane, which is what makes a
   *  marker dropped there mean the train comes off the layout. */
  private overRoster(screen: Point): boolean {
    return within(this.renderRoot.querySelector<TcRoster>("tc-roster"), screen);
  }

  /** Whether a screen point is over the drawing surface, which is what makes
   *  a row dropped there mean a placement. */
  private onCanvas(screen: Point): boolean {
    return within(this.canvas, screen);
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
      <tc-roster
        .trains=${this.roster}
        .run=${this.session === null ? null : (this.panel?.run ?? null)}
        @roster-dropped=${this.dropped}
      ></tc-roster>

      ${this.released === null
        ? nothing
        : html`<header><span class="released">${this.released}</span></header>`}
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
      placed: this.standing.length,
    };
  }

  /**
   * The trains the run has on the layout, and where each stands
   * (model/panel.ts). Worked out afresh on each render, being the last frame's
   * answer like everything else the picture says.
   *
   * Nothing, with no session joined, as the run's value and the supply's are.
   * `leave` keeps the model so that rejoining does not flash, but a page that
   * has left a session is being told nothing — and what this answers freezes
   * the drawing, which must not outlive the knowledge it rests on: a page
   * reloaded is not frozen, and a page that has left is in the same position.
   */
  private get standing(): Placed[] {
    if (this.session === null) return [];
    return this.panel?.placed() ?? [];
  }

  /** What the roster pane draws: every train the railroad owns, marked with
   *  where the run has it (`model/panel.ts`). Two sources because they are two
   *  things — the store says what stock there is, the bus says where it stands
   *  (ADR-0010) — and the pane is handed the answer rather than either. */
  private get roster(): RosterRow[] {
    return roster(this.stock, this.standing);
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
      was.trouble === now.trouble &&
      was.placed === now.placed
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

/** Whether a client point is inside an element's box. Where each part of the
 *  view sits is the browser's answer and nothing this file works out; an
 *  element that is not there holds no point at all. */
function within(part: Element | null, screen: Point): boolean {
  if (part === null) return false;
  const box = part.getBoundingClientRect();
  return (
    screen.x >= box.left &&
    screen.x <= box.right &&
    screen.y >= box.top &&
    screen.y <= box.bottom
  );
}
