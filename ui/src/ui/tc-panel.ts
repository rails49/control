/**
 * The run view (ui/PANEL.md): the drawing with the railroad's state painted on
 * top, fed by the broker it is a client of, and scheduling by drag and
 * turning a train around by right-click.
 *
 * The railroad it is painting is not its own — the app holds it and hands over
 * the drawing and the review
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * **The broker says which railroad it is**: one broker runs one railroad and
 * the layout interface publishes its name on a retained row
 * ([ADR-0059](../../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
 * decision 2), so this reads that row and the app loads the documents from the
 * store. It has no session of its own to choose: the band's picker asks for a
 * railroad on the bus and this carries the press, exactly as it carries the
 * band's power presses
 * ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)),
 * and what the page then shows is the row coming back — so the two cannot come
 * to name different ones.
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
 * view was built before there was anything live to join; a trace is the
 * harness's now, and the broker is the only thing that feeds a picture.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import mqtt, { type MqttClient } from "mqtt";
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
import {
  readTrains,
  RETRY_MS,
  said,
  UNREVIEWED,
  type Review,
  type TrainDoc,
} from "../model/store.js";
import { cabs, type Cab } from "../model/throttle.js";
import {
  DRAINING,
  gesture,
  Live,
  modeWanted,
  placement,
  powerWanted,
  railroadWanted,
  reversal,
  runWanted,
  throttleWanted,
  type Frame,
  type Mode,
  type Power,
  type Run,
  type TraceEvent,
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
  /** How the run stands, `null` while no session is joined or before the
   *  dispatcher has said (ADR-0037). It is what the bar's HOLD/GO reads. */
  run: Run | null;
  /** Whether a train may move at all, `null` while no session is joined or
   *  before the layout has said (ADR-0041). The band says which it is, and
   *  the bar's GO is greyed while it is anything but `on`. */
  power: Power | null;
  /** Whether the band's OFF is waiting on the drain: it has asked for
   *  `draining` and publishes `power_wanted: off` when the run reads `held`
   *  with nothing moving, and not before (ADR-0051, ADR-0062). The band says
   *  so on the button, a drain that never lands leaving the railroad
   *  powered. */
  draining: boolean;
  /** What a session refused, or the store not answering. Never a fault of the
   *  drawing itself: those are marked where they are (ADR-0024). */
  trouble: string | null;
  /** The trains the run has on the layout, by name. The bar reads how many
   *  there are as the rule that trains on the layout freeze the drawing
   *  (`model/commands.ts`, ADR-0038), and the stock screen reads which they
   *  are as the rule that a placed train's length may not be corrected
   *  (ui/STOCK.md): only this view knows, and neither of the two views where
   *  it is felt does. */
  placed: readonly string[];
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

/** Where the broker is, as the page it is asked from says.
 *
 *  One path on the page's own origin, `/mqtt`, which vite proxies in
 *  development and the reverse proxy strips in front of a layout server
 *  (docs/DEPLOY.md), so the URL the panel builds is the same either way. The
 *  scheme follows the page's: a plain `ws://` from a page served over TLS is
 *  mixed content and the browser refuses it, which is what a port of its own
 *  would have forced (ADR-0042).
 *
 *  `?broker=` overrides it for a broker somewhere else, and that is the whole
 *  of the browser's configuration — the railroad is not part of it, one
 *  broker running one railroad and saying which on a retained row (ADR-0059,
 *  decision 2).
 */
export function brokerAt(page: {
  protocol: string;
  host: string;
  search: string;
}): string {
  const named = new URLSearchParams(page.search).get("broker");
  if (named !== null) return named;
  const scheme = page.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${page.host || "localhost:5173"}/mqtt`;
}

const BROKER = brokerAt(location);

/** Everything of ours, which is the whole of what a page subscribes: the
 *  retained rows arrive as the subscription lands and the events follow
 *  (ADR-0032). One filter and not a list — the panel already reads a subset of
 *  what arrives (model/panel.ts), and a list here would be a second inventory
 *  to keep in step. */
const OURS = "tc49/#";

/** The row the layout interface publishes to say which railroad this broker
 *  runs ([#371](https://github.com/rails49/control/issues/371)). Read here and
 *  not applied to the model: it is the page's whole choice of railroad, and
 *  the picture is about the one it names. */
const RAILROAD = "tc49/layout/state/railroad";

/** How much of the bus is held while a page waits for its documents. The
 *  broker names the railroad and the store is then asked for the drawing it
 *  means, and everything published in between — the retained picture at the
 *  front of it — has nowhere to go until the model those documents build
 *  exists. A page whose documents never arrive draws nothing whatever it
 *  holds, so the hold stops here rather than growing without bound. */
const HELD = 1000;

@customElement("tc-panel")
export class TcPanel extends LitElement {
  static override styles = panelStyles;

  /** The loaded railroad, the app's own document. */
  @property({ attribute: false }) drawing: Drawing | null = null;

  /** What the store says that drawing means. A railroad that does not derive
   *  has no layout to paint on, and the band already says so. */
  @property({ attribute: false }) review: Review | null = null;

  /** Whether this view is the current one.
   *
   *  **The roster is read again when it becomes current.** The store is not on
   *  the bus, so nothing publishes a roster change (ADR-0010): a person who
   *  adds a locomotive on the stock screen and switches here must see it, and
   *  the run keeps the roster it joined with until then (ui/STOCK.md). It is
   *  the roster and not the session — the connection is untouched, and what the
   *  bus says about where the trains are is not re-read, because nothing about
   *  it went stale. The connection is untouched: it is the page's and not a
   *  view's. */
  @property({ type: Boolean }) current = false;

  /** The railroad the broker says it runs, `null` while it has not said —
   *  before the connection lands, and again after it has gone (#371). */
  @state() private session: string | null = null;
  @state() private connected = false;
  @state() private trouble: string | null = null;
  /** The railroad's roster: every train it owns, how long each is and what a
   *  person driving it can switch, read off the store when the session is
   *  joined (ADR-0039, ADR-0045). The bus says where the trains are and never
   *  what there is to place or what one is made of. */
  @state() private stock: Record<string, TrainDoc> = {};
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
   *  what says a fresh hold has begun — and, read the other way round, what
   *  says a run has been released. */
  private wasRunning = false;
  /** Whether an OFF is waiting on the drain (ADR-0051, ADR-0062). The press
   *  asks the run to drain and stops there; the supply is removed when
   *  `state/run` reads `held` with nothing moving, and the wait is dropped
   *  when the run word *changes* to `running`, that being a drain somebody
   *  abandoned. A row repeating the word the press was made against is the
   *  drain still outstanding, whatever `moving` now says (#441). */
  @state() private draining = false;
  /** The railroad the model was built for, so it is rebuilt when the app loads
   *  another and kept when anything else changes. */
  private built: string | null = null;
  /** Whether the canvas wants fitting once it has drawn: a railroad arrives
   *  here when the row the layout interface writes names another one, and
   *  there is nowhere else the viewport should be looking. */
  private fitting = false;
  private live: Live | null = null;
  /** The page's one connection to the broker, `null` before the view is on
   *  screen and after it has gone. It belongs to the page and not to a
   *  railroad: one broker runs one railroad (ADR-0059, decision 2), so it is
   *  opened once and kept. */
  private client: MqttClient | null = null;
  /** Whether the roster of the railroad the broker named has been read. The
   *  store is not on the bus, so a read that failed is retried until it
   *  lands — and a railroad that owns no stock is read, not empty. */
  private stocked = false;
  /** What arrived between the broker naming the railroad and the store
   *  answering for its documents, `null` when there is nothing to wait for.
   *  Retained values arrive as the subscription lands (ADR-0032) and there is
   *  no second delivery of them, so a page that dropped them would show an
   *  empty railroad until something happened to be published. */
  private held: TraceEvent[] | null = null;
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

  override connectedCallback(): void {
    super.connectedCallback();
    this.connect();
  }

  override disconnectedCallback(): void {
    this.leave();
    this.connected = false;
    const going = this.client;
    this.client = null;
    going?.end(true);
    this.live = null;
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
    if (changed.has("current") && this.current && this.session !== null) {
      void this.reread(this.session);
    }
    if (!changed.has("drawing") && !changed.has("review")) return;
    const name = this.drawing?.drawing ?? null;
    const layout = this.review?.layout ?? null;
    const explain = this.review?.explain ?? null;
    if (name === null || layout === null || explain === null) {
      if (name !== this.built) this.gone();
      return;
    }
    if (name === this.built) return;
    // A railroad swapped under a menu or a drag leaves both about a train on
    // the one that went.
    this.drag.cancel();
    this.menu = null;
    this.released = null;
    this.panel = new Panel(layout, explain, this.drawing!.wires);
    this.built = name;
    this.fitting = true;
    for (const event of this.held ?? []) this.panel.apply(event);
    this.held = null;
    this.wasRunning = this.panel.run === "running";
    this.beat++;
  }

  /** The railroad went away, or stopped deriving. There is nothing to paint,
   *  which is a fact about the documents and not about the bus: the broker
   *  goes on running the railroad it named, and the band says why nothing is
   *  drawn. */
  private gone(): void {
    this.panel = null;
    this.built = null;
    this.beat++;
  }

  // --- the broker, and the railroad it runs ---------------------------------

  /**
   * Open the page's one connection to the broker and subscribe everything of
   * ours.
   *
   * It is not a railroad's connection. One broker runs one railroad and says
   * which on a retained row (ADR-0059, decision 2), so this is opened when the
   * view is mounted and kept for as long as it is on screen; what changes
   * under it is which railroad the row names.
   *
   * **Getting back in is the client's own.** MQTT.js reconnects at `RETRY_MS`
   * and resubscribes, and a fresh subscription is answered with every retained
   * row (ADR-0032) — the picture the page had, republished. So there is no
   * retry of this view's here, and the only one left is the store's, the store
   * not being on the bus.
   */
  private connect(): void {
    this.live = new Live();
    const client = mqtt.connect(BROKER, {
      reconnectPeriod: RETRY_MS,
      // A page keeps nothing across a reload and wants the retained rows
      // again, which is what a clean session is.
      clean: true,
    });
    client.on("connect", () => {
      if (client !== this.client) return;
      // Every retained row is about to be replayed, so what the last
      // connection left in the model that no retained row will replace goes
      // first — an event is reported once and never comes round again.
      this.panel?.reset();
      this.connected = true;
      this.trouble = null;
      // Armed here and not where the railroad is named: the broker replays
      // every retained row under this filter, in an order the contract does
      // not fix, so rows land before the one that says which railroad they
      // are about. Anything arriving before the buffer exists is dropped, and
      // an event is never replayed, so parts of the picture would stay wrong
      // for the life of the page (ADR-0032).
      this.held = [];
      client.subscribe(OURS);
      this.beat++;
    });
    client.on("message", (topic, payload) => {
      if (client !== this.client) return;
      this.heard(topic, new TextDecoder().decode(payload));
    });
    client.on("close", () => {
      if (client !== this.client || !this.connected) return;
      // The broker has gone. What it was saying is no longer being said, so
      // the page holds no session at all: the roster empties, the drawing
      // thaws, and the picture the last frame left stays on screen with
      // nothing to gesture at.
      this.connected = false;
      this.leave();
      this.beat++;
    });
    client.on("error", () => {
      if (client !== this.client) return;
      this.trouble = `no broker at ${BROKER}`;
    });
    this.client = client;
  }

  /**
   * Which railroad this broker runs, as the layout interface says on its
   * retained row (#371).
   *
   * It is the whole of the page's choice. The app holds the loaded railroad
   * and hands the documents down (ADR-0038), so this says which and the app
   * reads it from the store. The picker asks on `railroad_wanted` and is
   * answered here or not at all: what a person pressed never loads anything
   * by itself (ADR-0060). The roster is read here because it is the railroad's
   * asset and not the run's — what stock there is to place, which no topic
   * carries (ADR-0039). Everything else comes off the bus: placement, locks
   * and live requests off the dispatcher's retained picture, facing off the
   * scheduler's (ADR-0032, ADR-0036).
   */
  private named(railroad: string): void {
    if (railroad === this.session) return;
    // What arrived before this row did, which is this railroad's and not the
    // last one's: on a fresh connection the panel is still null and the rows
    // buffered since `connect` are the retained picture being replayed around
    // us. `leave()` below drops the buffer, so it is carried over rather than
    // started again. A railroad swapped while a panel is up is the other
    // case — there rows are applied directly, the buffer is already null, and
    // there is nothing to carry.
    const early = this.panel === null ? this.held : null;
    this.leave();
    this.session = railroad;
    this.held = early ?? [];
    this.beat++;
    this.dispatchEvent(
      new CustomEvent<string>("railroad", {
        detail: railroad,
        bubbles: true,
        composed: true,
      }),
    );
    void this.read(railroad);
  }

  /** The railroad's roster, off the store. A read that fails says so and is
   *  tried again: the store is not on the bus, so nothing will republish it. */
  private async read(railroad: string): Promise<void> {
    try {
      const stock = await readTrains(railroad);
      if (this.session !== railroad) return;
      this.stock = stock.trains;
      this.stocked = true;
      this.trouble = null;
      this.beat++;
    } catch (failure) {
      // Which of the three it was is the store helper's to say (model/store.ts,
      // #411): a store that is not running, an answer that came from something
      // else, or the store refusing. A fixed string here named the fix for the
      // first whichever it was, and sent a person after a store that was up
      // (#405).
      if (this.session !== railroad) return;
      this.trouble = said(failure);
      this.retry();
    }
  }

  /**
   * The railroad's roster, read again over a session that is already up.
   *
   * Only the roster: the connection is open and every retained topic has been
   * replayed, so there is nothing else to go back for. A read that fails
   * leaves what the view already has — the roster it joined with is a better
   * answer than none, and the store not answering is already said elsewhere.
   */
  private async reread(railroad: string): Promise<void> {
    try {
      const stock = await readTrains(railroad);
      if (this.session === railroad) this.stock = stock.trains;
    } catch {
      // Kept as it was: see above.
    }
  }

  /** Read the roster again in a moment, unless a read is already waiting. Only
   *  one is ever waiting, so a second failure inside the interval does not
   *  start a second run of tries. */
  private retry(): void {
    if (this.waiting !== null) return;
    this.waiting = setTimeout(() => {
      this.waiting = null;
      const railroad = this.session;
      if (railroad !== null && !this.stocked) void this.read(railroad);
    }, RETRY_MS);
  }

  private heard(topic: string, payload: string): void {
    if (this.live === null) return;
    const event = this.live.read(topic, payload);
    if (event === null) return;
    if (topic === RAILROAD) {
      const name = event["name"];
      if (typeof name === "string") this.named(name);
      return;
    }
    if (this.panel === null) {
      if (this.held !== null && this.held.length < HELD) this.held.push(event);
      return;
    }
    this.panel.apply(event);
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
    const was = this.wasRunning;
    const running = this.panel.run === "running";
    if (was && !running) this.released = null;
    this.wasRunning = running;
    // The wait the OFF press started is decided by the run's own row and by
    // nothing else: the value standing between the press and the
    // dispatcher's answer is the one the press was made against, so a frame
    // about anything else leaves the wait alone.
    if (this.draining && event.event === "run") {
      if (running && !was) {
        // A drain somebody abandoned — this panel's GO or another's — and the
        // wait goes with it. Left standing, a HOLD hours later would cut the
        // power out of a press the person had moved on from (ADR-0062).
        //
        // The word changing and not the word: the dispatcher republishes the
        // row whenever `moving` moves under a standing run word, so a running
        // run whose last train arrives says `running` again (#406) — the drain
        // still outstanding, not one released. Reading the value there dropped
        // the wait, the later `held` did nothing, and the supply stayed on with
        // the button back to *OFF* (#441).
        this.draining = false;
      } else if (this.drained) {
        // The drain has landed, so the supply goes now and not before:
        // nothing is crossing, nothing is committed, and every grant
        // re-aligns, so the point positions the cut costs cost nothing
        // (ADR-0051). A run that never drains leaves the railroad powered
        // and the button saying it is still waiting.
        this.cut();
      }
    }
    this.beat++;
  }

  /**
   * Hold the run, or release it: one `run_wanted` naming where it should
   * stand (ADR-0037). The app presses it on the bar, the client is here, and
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
    // `connected` and not merely a client: MQTT.js queues a publish made
    // while it is reconnecting, and the notice below would then stand for a
    // release the dispatcher never heard.
    if (!this.connected || this.panel === null) return;
    this.released = run === "running" ? outstanding(this.panel.disputes()) : null;
    this.send(runWanted(run));
  }

  /**
   * ON, STOP or OFF, pressed on the band: what the whole railroad's supply
   * should be doing ([ADR-0051](../../../docs/adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)).
   * The client is this view's, so the press comes here, as HOLD and GO do.
   *
   * **OFF is the drain trigger and never an immediate cut.** It asks the run
   * to drain — always, a held run included, because a held run can still be
   * moving — and waits for `state/run` to read `held` with nothing moving; an
   * abrupt `off` would leave no point position trustworthy and strand
   * whatever was mid-transit. `layout` refuses an `off` it should not apply
   * ([ADR-0062](../../../docs/adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)),
   * so this wait is the person's view of the drain rather than the only
   * guard; the panel still does not send `off` blindly.
   *
   * ON and STOP go out at once, and each abandons a wait the drain left
   * standing: the person has said what they want the supply to do, and a cut
   * arriving later out of a press they have moved on from is exactly the
   * surprise this button exists to avoid. Neither writes `run_wanted` —
   * returning to `on` releases nothing on its own (ADR-0041), and an
   * emergency stop asks the rails for less rather than the run for more.
   */
  pressPower(power: Power): void {
    if (!this.connected || this.panel === null) return;
    if (power === "off") {
      this.draining = true;
      this.send(runWanted(DRAINING));
      // A run already held with nothing moving has nothing left to drain —
      // which is the whole of what the wait waits for — and the dispatcher
      // answering `held` with `held` publishes no frame for `heard` to see,
      // so the wait would never end.
      if (this.drained) this.cut();
      return;
    }
    this.draining = false;
    this.send(powerWanted(power));
  }

  /**
   * A railroad chosen in the band: one `railroad_wanted` naming it
   * ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
   * The client is this view's, so the press comes here, as the band's power
   * presses do.
   *
   * It asks and does not load. Whichever binding of the layout interface is
   * running answers it and publishes `tc49/layout/state/railroad`, and what
   * the page shows is that row coming back — so a gesture refused because the
   * rails have power, or because the store has no such railroad, leaves the
   * page on the railroad that is still running rather than on the one nobody
   * loaded (ADR-0035).
   */
  pressRailroad(railroad: string): void {
    this.send(railroadWanted(railroad));
  }

  /**
   * Take a train in a throttle, or give it back: one `mode_wanted` naming the
   * train and where its mode should stand
   * ([#207](https://github.com/rails49/control/issues/207)).
   *
   * The throttle view is another view of this app and holds no session, so
   * its gestures come here, exactly as the band's power presses do — one
   * client per page, and the topics are ones this view already writes.
   * `layout` answers by publishing `state/mode`, and the view reads who is
   * driving off that rather than off its own press (ADR-0035).
   */
  pressMode(train: string, mode: Mode): void {
    this.send(modeWanted(train, mode));
  }

  /** The throttle turned: one `throttle_wanted` carrying the number the lever
   *  shows. One signed speed for the train — which locomotive it reaches, and
   *  which way round that one stands, is `layout`'s (CONTEXT.md,
   *  **Throttle**). */
  pressThrottle(train: string, speed: number): void {
    this.send(throttleWanted(train, speed));
  }

  /** Turn a train round where it stands, from the throttle: the same
   *  `reversal_wanted` this view's own menu writes, the scheduler flipping
   *  the facing and nothing moving (ADR-0019). */
  pressReversal(train: string): void {
    this.send(reversal(train));
  }

  /** One frame, published on its own topic. `connected` and not merely a
   *  client: MQTT.js queues a publish made while it is reconnecting, and a
   *  gesture nobody heard must not look like one that landed. */
  private send(frame: Frame): void {
    if (this.client === null || !this.connected) return;
    this.client.publish(frame.topic, JSON.stringify(frame.payload));
  }

  /** Whether the drain has landed: the run reads `held` and the row says
   *  nothing is moving. Both conditions and not the word alone — a held run
   *  can be moving, a move already granted running to its sensor, and a
   *  person's HOLD writes `held` with trains still rolling (ADR-0062).
   *
   *  `moving === false` and not merely a falsy one: a row without the field
   *  is an older dispatcher saying nothing about what is under way, and it
   *  never lets this button cut. `layout`'s guard applies such an `off`
   *  because a guard refuses on evidence and an absence is none; the wait is
   *  the other way round, because what it risks is a train stranded where no
   *  sensor will ever say it stopped, and all it costs is a button that goes
   *  on saying *DRAINING…* against a dispatcher too old to answer it. */
  private get drained(): boolean {
    return this.panel !== null && this.panel.run === "held" && this.panel.moving === false;
  }

  /** The supply removed, once the drain has landed. */
  private cut(): void {
    this.draining = false;
    this.send(powerWanted("off"));
  }

  /** The session goes: the broker has stopped answering, or it has named
   *  another railroad. What the model holds is kept — a page getting back in
   *  must not flash — and everything the last session put on screen of its own
   *  goes. */
  private leave(): void {
    if (this.waiting !== null) clearTimeout(this.waiting);
    this.waiting = null;
    this.drag.cancel();
    this.menu = null;
    this.stock = {};
    this.stocked = false;
    this.released = null;
    this.wasRunning = false;
    this.held = null;
    // A session going away takes the wait with it: the run whose drain was
    // being watched is no longer being reported on, and a cut fired at the
    // next session's first `held` would be this one's press arriving late.
    this.draining = false;
    this.session = null;
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
   * dispatcher's answer comes back over the same connection and renders itself.
   *
   * The machine calls it, the canvas having driven the gesture: writing to the
   * bus is this view's and no model's.
   */
  private submit(drop: Drop): void {
    if (this.panel === null) return;
    this.send(gesture(this.panel.compose(drop.train, drop.dest)));
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
    this.send(placement(train, block));
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
    this.send(placement(train, null));
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
    this.send(reversal(train));
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
      run: this.session === null ? null : (this.panel?.run ?? null),
      power: this.session === null ? null : (this.panel?.power ?? null),
      draining: this.draining,
      trouble: this.trouble,
      placed: this.standing.map(({ train }) => train),
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

  /**
   * What the throttle view draws: one cab per train the railroad has placed
   * (`model/throttle.ts`, ui/THROTTLE.md).
   *
   * Worked out here because everything it is made of is here — the run's
   * picture, `layout`'s modes, the scheduler's facing, the dispatcher's
   * aspects and the railroad's roster — and handed up whole, the throttle
   * being a view of this app with no session of its own. Nothing of the
   * throttle's own is in it: which train a person picked and where they have
   * put the lever are theirs, and live in the view with the pointer.
   */
  private get driving(): Cab[] {
    const model = this.panel;
    if (model === null || this.session === null) return [];
    const placed = model.placed();
    return cabs({
      placed,
      modes: model.modes(),
      noses: model.noses(),
      aspects: model.aspects(),
      ahead: model.ahead(),
      inFlight: new Set(
        placed.filter(({ train }) => model.inFlight(train)).map(({ train }) => train),
      ),
      stock: this.stock,
    });
  }

  /** The last status the app was told, so it is told again only when one of
   *  them has moved. */
  private said: RunStatus | null = null;

  /** The cabs the app was last told, written out: the array is built afresh
   *  on every render, so what one frame's answer is compared against is its
   *  text. The same care `run-status` takes field by field, and for the same
   *  reason — the app holds what it is told, so telling it again on a frame
   *  that changed nothing would re-render the whole page on every event the
   *  bus carries. */
  private saidCabs = "";

  /** The throttle's cabs, where they have moved: they are the last frame's
   *  answer like everything else the picture says (ui/THROTTLE.md). The app
   *  holding them sets no property of this view to a new value, so nothing
   *  comes back round. */
  private tellCabs(): void {
    const now = this.driving;
    const written = JSON.stringify(now);
    if (written === this.saidCabs) return;
    this.saidCabs = written;
    this.dispatchEvent(
      new CustomEvent<Cab[]>("cabs", { detail: now, bubbles: true, composed: true }),
    );
  }

  override updated(): void {
    if (this.fitting) {
      this.fitting = false;
      this.canvas?.fit();
    }
    this.tellCabs();
    const now = this.status;
    const was = this.said;
    if (
      was !== null &&
      was.joined === now.joined &&
      was.linked === now.linked &&
      was.run === now.run &&
      was.power === now.power &&
      was.draining === now.draining &&
      was.trouble === now.trouble &&
      same(was.placed, now.placed)
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

/** Whether two lists of placed trains say the same thing. The status is
 *  compared field by field so the app is told only when something moved, and
 *  a list is built afresh on every render. */
function same(was: readonly string[], now: readonly string[]): boolean {
  return was.length === now.length && was.every((train, at) => train === now[at]);
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
