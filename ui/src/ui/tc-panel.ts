/**
 * The run view (ui/PANEL.md): the drawing with the railroad's state painted on
 * top — the panel model the app's session feeds — and scheduling by drag and
 * turning a train around or cancelling its request by right-click.
 *
 * The railroad it is painting is not its own — the app holds it and hands over
 * the drawing and the review
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * Nor is the broker's connection: the session is the app's
 * (`model/session.ts`, #756), which reads the row that says which railroad
 * the broker runs, feeds the panel model, and carries every press. This view
 * reads the model off it and hands it the gestures it composes, and imports
 * nothing of MQTT.
 *
 * **It draws none of it.** `tc-canvas` in run mode is the surface, the same one
 * the editor draws on, so the viewport, the wires, the symbols and the labels
 * are written once and this view has zoom, pan and fit for free
 * ([#168](https://github.com/rails49/control/issues/168)). What this holds is
 * what only the run view has: the overlay it hands the canvas, the machine
 * that says what a drag means (model/drag.ts), the right-click menu, the
 * roster pane and the request list under it.
 *
 * Everything shown is the panel model's answer (model/panel.ts). It computes
 * nothing: occupancy, aspects, markers, the lit route, arrival ends and
 * whether a train is busy all arrive as data.
 *
 * Its one source is the bus (ADR-0038). Reading a recorded trace was how this
 * view was built before there was anything live to join; a trace is the
 * harness's now, and the broker is the only thing that feeds a picture.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import {
  blockAt,
  Drag,
  schedulingMachine,
  type Drop,
  type Painted,
} from "../model/drag.js";
import type { Drawing } from "../model/drawing.js";
import type { Point } from "../model/geometry.js";
import { roster, takenOff, type Overlay, type Panel, type RosterRow } from "../model/panel.js";
import { pointsOffered, positionsBySymbol } from "../model/scene.js";
import type { Session } from "../model/session.js";
import { UNREVIEWED, type Review } from "../model/store.js";
import {
  cancellation,
  gesture,
  placement,
  pointWanted,
  reorderWanted,
  reversal,
} from "../model/trace.js";
import { panelStyles } from "./tc-panel.styles.js";
import "./tc-canvas.js";
import "./tc-menu.js";
import "./tc-requests.js";
import "./tc-roster.js";
import type { TcCanvas } from "./tc-canvas.js";
import type { MenuItem } from "./tc-menu.js";
import type { RequestCancel, RequestReorder } from "./tc-requests.js";
import type { RosterDrag, TcRoster } from "./tc-roster.js";

/** What the right-click found, as the canvas hands it over: `trainAt`'s answer
 *  with the pointer's position on it (model/drag.ts). It is also what the open
 *  menu is, there being nothing else to remember about one. */
interface Clicked {
  x: number;
  y: number;
  block: string;
  train: string;
}

/** The actions the panel's menu offers, named once so the items and the
 *  handler cannot drift apart. */
const TURN_AROUND = "turn-around";
const CANCEL_REQUEST = "cancel-request";

@customElement("tc-panel")
export class TcPanel extends LitElement {
  static override styles = panelStyles;

  /** The loaded railroad, the app's own document. */
  @property({ attribute: false }) drawing: Drawing | null = null;

  /** What the store says that drawing means. A railroad whose drawing is
   *  invalid has no layout to paint on, and the band already says so. */
  @property({ attribute: false }) review: Review | null = null;

  /** Whether this view is the current one. */
  @property({ type: Boolean }) current = false;

  /** The page's session, the app's (`model/session.ts`, #756): the panel
   *  model this paints from, the run's status, and where a gesture goes.
   *  `null` before the app is on the page and after it has gone. The app
   *  asks this view to update whenever the session says something moved. */
  @property({ attribute: false }) session: Session | null = null;

  /** The open right-click menu: where it hangs, and the block and train it
   *  is about, `null` for none. */
  @state() private menu: Clicked | null = null;

  /** The panel model last painted, so a new one — another railroad, or the
   *  one loaded deriving again — is fitted to once and takes down a drag and
   *  a menu that were about the last. */
  private shown: Panel | null = null;
  /** The railroad the session was joined to when this last painted, `null`
   *  for none: a session that goes, or names another railroad, leaves a drag
   *  or a menu about a train on the one that went. */
  private joined: string | null = null;
  /** Whether the canvas wants fitting once it has drawn: a railroad arrives
   *  here when the row the layout interface writes names another one, and
   *  there is nowhere else the viewport should be looking. */
  private fitting = false;
  private readonly drag = new Drag();
  /** What a press on the canvas means here (model/drag.ts), bound to what is
   *  on screen. It answers quiet while there is no session to submit to,
   *  which is the whole of the gate on gesturing. */
  private readonly machine = schedulingMachine(this.drag, {
    painted: () => this.painted,
    submit: (drop) => this.submit(drop),
    remove: (train) => this.lift(train),
    throwPoint: (wanted) => this.session?.send(pointWanted(wanted)),
    onRoster: (screen) => this.overRoster(screen),
  });

  /**
   * What the session says now, against what this last painted.
   *
   * A railroad swapped under a menu or a drag, or a session that went, leaves
   * both about a train on the one that went. An open menu is about one train
   * in one block, and the run can end both: it is taken down rather than
   * hidden, a menu merely filtered out of the render leaving nothing to
   * dismiss and springing back the next time that train stands there.
   */
  override willUpdate(): void {
    const panel = this.panel;
    const status = this.session?.status;
    const joined = status?.joined ? status.railroad : null;
    if (panel !== this.shown || joined !== this.joined) {
      this.drag.cancel();
      this.menu = null;
    }
    if (panel !== this.shown && panel !== null) this.fitting = true;
    this.shown = panel;
    this.joined = joined;
    const at = this.menu;
    if (at !== null && (panel === null || !panel.shows(at.train, at.block))) this.menu = null;
  }

  /** The panel model the session built for the loaded railroad. */
  private get panel(): Panel | null {
    return this.session?.panel ?? null;
  }

  /** Whether the broker is answering. */
  private get linked(): boolean {
    return this.session?.status.linked ?? false;
  }

  /** Whether the session is joined to the railroad the broker names. */
  private get inSession(): boolean {
    return this.session?.status.joined ?? false;
  }

  // --- scheduling by drag ---------------------------------------------------

  /** Whether a drag means anything: only a joined session has anywhere to
   *  gesture at, and only there does a train look like something to pick up. */
  private get scheduling(): boolean {
    return this.linked && this.drawing !== null && this.panel !== null;
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
      offered: pointsOffered(drawing, model.lit().legs, model.positionsByAddress()),
    };
  }

  /**
   * The drop: one `request_wanted`, filter-free (ui/PANEL.md). The gesture
   * names the train and where to put it, and the scheduler composes the
   * request — the id and the departure end are its (ADR-0036). The
   * dispatcher's answer comes back over the same connection and renders itself.
   *
   * The machine calls it, the canvas having driven the gesture: composing it
   * is this view's, and the session carries it.
   */
  private submit(drop: Drop): void {
    if (this.panel === null) return;
    this.session?.send(gesture(this.panel.compose(drop.train, drop.dest)));
  }

  // --- putting a train on the layout, and taking it off ---------------------
  //
  // The roster's two drags (ADR-0039). **The source decides what a drag
  // means**, never the run's state: a row picked up in the pane places its
  // train, a marker picked up on the canvas asks for a request, and one motion
  // cannot come to mean two things depending on a word in the band. Both are
  // live at any power (ADR-0080): a placement only into a free block, a
  // removal anywhere, the dispatcher keeping what still reads occupied until
  // it reads clear (ADR-0069).

  /**
   * A row let go somewhere: one `placement_wanted` naming the block under the
   * pointer, or nothing where there is no block there or the block is not
   * free — a train stands in it, another holds its lock, or it is on another
   * train's remaining route (`Panel.free`). The dispatcher would drop that
   * placement, so it is not sent.
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
    if (painted === null || at === null || this.panel === null) return;
    const block = blockAt(painted.drawing, painted.review, at);
    if (block === null || !this.panel.free(block, train)) return;
    this.session?.send(placement(train, block));
  }

  /**
   * A marker dropped on the pane: the train comes off the layout, one
   * `placement_wanted` with no block.
   *
   * The dispatcher releases what it held and answers `train_removed`, and the
   * marker leaves the canvas because the picture no longer has the train —
   * this view retracts nothing of its own. In any run state (ADR-0069): a
   * train taken off while running leaves its occupied blocks held until they
   * read clear.
   */
  private lift(train: string): void {
    this.session?.send(placement(train, null));
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

  // --- the right-click menu -------------------------------------------------

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
   * The two items the panel offers, each greyed by whether that train has a
   * request in flight: the panel's only pre-judgement of a gesture, against
   * the filter-free drag where every drop submits (ui/PANEL.md). "Turn
   * around" is greyed while it has one and "Cancel request" while it has
   * none (ADR-0049).
   * "Turn around" and not "Reverse", which is the throttle's word, this
   * moving nothing.
   *
   * Worked out afresh on every event, so the items change the moment the
   * request is answered.
   */
  private get offered(): MenuItem[] {
    const at = this.menu;
    if (at === null || this.panel === null) return [];
    const busy = this.panel.inFlight(at.train);
    return [
      { label: "Turn around", action: TURN_AROUND, disabled: busy },
      { label: "Cancel request", action: CANCEL_REQUEST, disabled: !busy },
    ];
  }

  /** Chosen: one `reversal_wanted` naming the train, the scheduler flipping
   *  its facing and the arrow following, or one `cancel_wanted` naming the
   *  train's first request, the lit route going out when the dispatcher's
   *  picture drops it and those chained after it. */
  private chose(event: CustomEvent<string>): void {
    const train = this.menu?.train;
    this.menu = null;
    if (train === undefined) return;
    if (event.detail === TURN_AROUND) this.session?.send(reversal(train));
    if (event.detail === CANCEL_REQUEST) {
      const id = this.panel?.firstRequest(train) ?? null;
      if (id !== null) this.session?.send(cancellation(id));
    }
  }

  // --- the request list ---------------------------------------------------

  /** A row's cancel: one `cancel_wanted` naming that request, the requests
   *  chained after it ending with it (ADR-0080). */
  private cancelled(event: CustomEvent<RequestCancel>): void {
    this.session?.send(cancellation(event.detail.id));
  }

  /** A row let go elsewhere in the list: one `reorder_wanted`. The list
   *  redraws when the dispatcher's picture says the order changed, not
   *  before. */
  private reordered(event: CustomEvent<RequestReorder>): void {
    const { id, before } = event.detail;
    this.session?.send(reorderWanted(id, before));
  }

  // --- painting -------------------------------------------------------------

  override render() {
    const drawing = this.drawing;
    const live = this.overlay;
    // The trains a rebuild took off, one line each, for as long as the
    // dispatcher lists them (#709): only while there is something to say.
    const off = this.inSession ? takenOff(this.panel?.unfit() ?? []) : [];
    return html`
      <aside>
        <tc-roster
          .trains=${this.roster}
          .live=${this.inSession}
          @roster-dropped=${this.dropped}
        ></tc-roster>
        <tc-requests
          .requests=${this.inSession ? (this.panel?.requestList() ?? []) : []}
          ?live=${this.inSession}
          @request-cancelled=${this.cancelled}
          @request-reordered=${this.reordered}
        ></tc-requests>
      </aside>

      ${off.length === 0
        ? nothing
        : html`<header>
            ${off.map((line) => html`<span class="unfit">${line}</span>`)}
          </header>`}
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

  /** What the roster pane draws: every train the railroad owns, marked with
   *  where the run has it (`model/panel.ts`). Two sources because they are two
   *  things — the store says what stock there is, the bus says where it stands
   *  (ADR-0010) — and the pane is handed the answer rather than either. */
  private get roster(): RosterRow[] {
    const session = this.session;
    return session === null ? [] : roster(session.owned, session.standing);
  }

  override updated(): void {
    if (this.fitting) {
      this.fitting = false;
      this.canvas?.fit();
    }
  }

  /**
   * What the run has painted over the drawing, for the canvas to draw (#168).
   *
   * Every entry is the panel model's own answer, worked out afresh on each
   * render because each is the last frame's. Point positions, and the throws
   * a click on a point would ask for, are what the model cannot answer alone:
   * they are commanded by address, and the drawing is what turns an address
   * back into a symbol (ADR-0022, ADR-0068, ui/PANEL.md).
   */
  private get overlay(): Overlay | null {
    const model = this.panel;
    if (model === null || this.drawing === null) return null;
    const lit = model.lit();
    const commanded = model.positionsByAddress();
    return {
      blocks: model.blocks(),
      lit,
      aspects: model.aspects(),
      detected: model.detected(),
      positions: positionsBySymbol(this.drawing, commanded),
      offered: pointsOffered(this.drawing, lit.legs, commanded),
      markers: model.markers(),
    };
  }

  // --- the viewport, which is the canvas's ----------------------------------

  /** Zoom and fit, pressed on the rail or typed on the keyboard. The app asks
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