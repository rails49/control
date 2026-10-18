/**
 * The page's one connection to the broker, and everything that follows from
 * it (#756): the railroad the broker's row names, the run's picture the bus
 * feeds, track power, HOLD/GO and the release notice, and the OFF drain.
 *
 * **A session is the page joined to the railroad the broker names**
 * (ui/PANEL.md). One broker runs one railroad and the layout interface
 * publishes its name on a retained row
 * ([ADR-0059](../../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
 * decision 2), so this reads that row and says which through `named`, and the
 * app has the loaded railroad read the documents off the store and hands them
 * back through `documents`. It has no session of its own to choose: the
 * settings dialog asks for a railroad on the bus and this carries the press,
 * exactly as it carries the band's power presses
 * ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)),
 * and what the page then shows is the row coming back — so the two cannot come
 * to name different ones.
 *
 * Every view reads it and none holds it. The app holds the one session, sends
 * every press here, and hands the views what this answers: the run view the
 * panel model it paints from, the throttle its cabs, the band and the stock
 * view the run's status (ADR-0038, ui/THROTTLE.md).
 *
 * No DOM, as nothing under `model/` has (docs/ARCHITECTURE.md). The page's
 * address comes in as `url` and the client as `connect`, so a suite drives
 * the broker's side of it with nothing mounted.
 */

import mqtt from "mqtt";

import type { Drawing } from "./drawing.js";
import { outstanding, Panel, type Placed } from "./panel.js";
import { RETRY_MS, type Review, type TrainDoc } from "./store.js";
import { cabs, type Cab } from "./throttle.js";
import {
  DRAINING,
  Live,
  modeWanted,
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
} from "./trace.js";

/**
 * What the session knows about the run that the band and the rail do not:
 * whether a session is joined and answering, how far it has got, and what it
 * refused. One object carries all of it, because they change together and the
 * app keeps one copy.
 */
export interface RunStatus {
  joined: boolean;
  /** The railroad the broker says it runs, `null` while it has not said
   *  (#371) and `""` where it says it runs none (#727). The app reads it to know whether the open drawing is the loaded
   *  railroad, whose save names it again and whose unsaved edits hold ON
   *  (`model/commands.ts`, ADR-0071). */
  railroad: string | null;
  linked: boolean;
  /** How the run stands, `null` while no session is joined or before the
   *  dispatcher has said (ADR-0037). It is what the rail's HOLD/GO reads. */
  run: Run | null;
  /** Whether a train may move at all, `null` while no session is joined or
   *  before the layout has said (ADR-0041). The band says which it is, and
   *  the rail's GO is greyed while it is anything but `on`. */
  power: Power | null;
  /** Whether the band's OFF is waiting on the drain: it has asked for
   *  `draining` and publishes `power_wanted: off` when the run reads `held`
   *  with nothing moving, and not before (ADR-0062, ADR-0074). The band says
   *  so on the button, a drain that never lands leaving the railroad
   *  powered. */
  draining: boolean;
  /** What a session refused, or the store not answering. Never a fault of the
   *  drawing itself: those are marked where they are (ADR-0024). */
  trouble: string | null;
  /** What the hardware says is wrong with the supply, in its own words,
   *  `null` where it says nothing (BUS.md, device vocabulary). The band shows
   *  it as a fault beside the trouble: that one is the app's and this one is
   *  the railroad's, and a tripped district is said nowhere else
   *  ([ADR-0050](../../../docs/adr/0050-broken-hardware-is-reported-never-worked-around.md),
   *  [#602](https://github.com/rails49/control/issues/602)). */
  fault: string | null;
  /** The trains the run has on the layout, by name. The stock screen marks
   *  their rows "on the layout" (ui/STOCK.md). */
  placed: readonly string[];
}

/** What the session says about itself before it has said anything. */
export const QUIET: RunStatus = {
  joined: false,
  railroad: null,
  linked: false,
  run: null,
  power: null,
  draining: false,
  trouble: null,
  fault: null,
  placed: [],
};

/**
 * The client, as far as a session uses one: the five calls `mqtt.connect`
 * hands back, and the same five `test/support/broker.ts` stands for. Any more
 * of MQTT.js here would be surface a suite's broker has to fake.
 */
export interface Client {
  on(event: "connect" | "close" | "error", listener: () => void): unknown;
  on(event: "message", listener: (topic: string, payload: Uint8Array) => void): unknown;
  subscribe(filter: string): unknown;
  publish(topic: string, payload: string): unknown;
  end(force?: boolean): unknown;
}

/** What the session tells the app holding it. */
export interface Hooks {
  /** Something the session answers may have moved: a frame was applied, or
   *  the connection or the session changed. */
  notify(): void;
  /** The broker's row named a railroad, `""` for none (#727). The app has
   *  the loaded railroad read its documents and hands them back through
   *  `documents`. */
  named(railroad: string): void;
}

/** Where the broker is, as the page it is asked from says.
 *
 *  One path on the page's own origin, `/mqtt`, which vite proxies in
 *  development and the reverse proxy strips in front of a layout server
 *  (docs/DEPLOY.md), so the URL the page builds is the same either way. The
 *  scheme follows the page's: a plain `ws://` from a page served over TLS is
 *  mixed content and the browser refuses it, which is what a port of its own
 *  would have forced (ADR-0042).
 *
 *  `?broker=` overrides it for a broker somewhere else, and that is the whole
 *  of the browser's configuration — the railroad is not part of it, one
 *  broker running one railroad and saying which on a retained row (ADR-0059,
 *  decision 2).
 *
 *  The app asks it of `location`; nothing under `model/` reads that.
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

/**
 * What the band says while the broker at `url` is not answering, which is the
 * whole of what it says about the link (#517).
 *
 * It names the address the page is trying and the one thing a person can do
 * about it, because a bare "not connected" leaves them with a working app and
 * no idea which of five containers is down. The broker is the first hop and
 * the only one this page opens itself — the store is asked over HTTP and says
 * so in its own words — so naming it is naming what to look at.
 *
 * Exported so the suite reads the words off this module rather than respelling
 * them, the way it reads `RETRY_MS`.
 */
export function gone(url: string): string {
  return `no broker at ${url} — is the bus running?`;
}

/** The page's client, as MQTT.js opens one. **Getting back in is the
 *  client's own**: it reconnects at `RETRY_MS` and resubscribes, and a fresh
 *  subscription is answered with every retained row (ADR-0032) — the picture
 *  the page had, republished. A page keeps nothing across a reload and wants
 *  the retained rows again, which is what a clean session is. */
export function connecting(url: string): Client {
  return mqtt.connect(url, { reconnectPeriod: RETRY_MS, clean: true });
}

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
export const HELD = 1000;

export class Session {
  /** The panel model the bus feeds, `null` while the loaded railroad has no
   *  layout to build one from (model/panel.ts). The run view paints from it. */
  panel: Panel | null = null;

  /** What the band and the rail read off the run: the same object until one
   *  of its fields moves, so the app holding it redraws only then. */
  status: RunStatus = QUIET;

  /** What the throttle view draws, one cab per train placed
   *  (`model/throttle.ts`): the same array until what it says moves. */
  cabs: readonly Cab[] = [];

  /** What was still disputed at the moment the hold was released, in words,
   *  `null` while there is nothing to say. */
  released: string | null = null;

  /** The railroad the broker says it runs, `null` while it has not said —
   *  before the connection lands, and again after it has gone (#371). */
  private session: string | null = null;
  /** Whether the row names no railroad, `""`: there is no session to join,
   *  but the broker has said, which is not the same as not having said. */
  private nameless = false;
  private connected = false;
  private trouble: string | null = null;
  /** Whether the run was running when the last frame was applied, which is
   *  what says a fresh hold has begun — and, read the other way round, what
   *  says a run has been released. */
  private wasRunning = false;
  /** Whether an OFF is waiting on the drain (ADR-0062, ADR-0074). The press
   *  asks the run to drain and stops there; the supply is removed when
   *  `state/run` reads `held` with nothing moving, and the wait is dropped
   *  when the run word *changes* to `running`, that being a drain somebody
   *  abandoned. A row repeating the word the press was made against is the
   *  drain still outstanding, whatever `moving` now says (#441). */
  private draining = false;
  /** The railroad the model was built for, so it is rebuilt when the app loads
   *  another and kept when anything else changes. */
  private built: string | null = null;
  /** The loaded railroad's trains, as `documents` was last handed them. */
  private trains: Record<string, TrainDoc> = {};
  private live: Live | null = null;
  /** The page's one connection to the broker, `null` after it has gone. It
   *  belongs to the page and not to a railroad: one broker runs one railroad
   *  (ADR-0059, decision 2), so it is opened once and kept. */
  private client: Client | null = null;
  /** What arrived between the broker naming the railroad and the store
   *  answering for its documents, `null` when there is nothing to wait for.
   *  Retained values arrive as the subscription lands (ADR-0032) and there is
   *  no second delivery of them, so a page that dropped them would show an
   *  empty railroad until something happened to be published. */
  private held: TraceEvent[] | null = null;
  /** The cabs as last answered, written out: the array is built afresh on
   *  every frame, so what one frame's answer is compared against is its
   *  text. */
  private saidCabs = "[]";

  constructor(
    private readonly url: string,
    connect: (url: string) => Client,
    private readonly hooks: Hooks,
  ) {
    this.connect(connect);
  }

  /** The connection let go of: the page is going. */
  end(): void {
    this.leave();
    this.connected = false;
    const going = this.client;
    this.client = null;
    going?.end(true);
    this.live = null;
    this.settle();
  }

  /**
   * The app loaded a railroad, or reviewed the one that is loaded again: the
   * loaded railroad's drawing, what the store says it means, and its trains.
   * Called on every render of the app.
   *
   * The model is built once per railroad and kept across everything else. One
   * built afresh would forget what the bus has shown it, and only the next
   * picture would bring any of it back. So it is rebuilt only when the
   * drawing's name changes or the review starts or stops deriving. A railroad
   * that does not derive has no layout to build from, so nothing is painted
   * and the band says why — a fact about the documents and not about the bus:
   * the broker goes on running the railroad it named.
   *
   * It notifies nothing, the app being mid-render when it calls; what moved is
   * read off `panel`, `status` and `cabs` straight after.
   */
  documents(
    drawing: Drawing | null,
    review: Review | null,
    trains: Record<string, TrainDoc>,
  ): void {
    this.trains = trains;
    const name = drawing?.drawing ?? null;
    const layout = review?.layout ?? null;
    const explain = review?.explain ?? null;
    if (name === null || layout === null || explain === null) {
      if (name !== this.built) {
        this.panel = null;
        this.built = null;
      }
    } else if (name !== this.built) {
      this.released = null;
      this.panel = new Panel(layout, explain, drawing!.wires);
      this.built = name;
      for (const event of this.held ?? []) this.panel.apply(event);
      this.held = null;
      this.wasRunning = this.panel.run === "running";
    }
    this.settle();
  }

  // --- the broker, and the railroad it runs ---------------------------------

  /**
   * Open the page's one connection to the broker and subscribe everything of
   * ours.
   *
   * It is not a railroad's connection. One broker runs one railroad and says
   * which on a retained row (ADR-0059, decision 2), so this is opened when the
   * session is made and kept; what changes under it is which railroad the row
   * names. Getting back in is the client's own (`connecting`), so there is no
   * retry here: the store's is the loaded railroad's (`model/railroad.ts`),
   * the store not being on the bus.
   */
  private connect(connect: (url: string) => Client): void {
    this.live = new Live();
    const client = connect(this.url);
    this.client = client;
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
      this.changed();
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
      // Said here as well as on `error`, and in the same words. The band draws
      // no "connected" of its own any more (#517): a link that is up is the
      // ordinary case and says nothing, so the one time it has to speak is the
      // time it is down, and a page that lost the broker mid-run must not go
      // quiet just because the connection opened once.
      this.trouble = gone(this.url);
      this.leave();
      this.changed();
    });
    client.on("error", () => {
      if (client !== this.client) return;
      this.trouble = gone(this.url);
      this.changed();
    });
  }

  /**
   * Which railroad this broker runs, as the layout interface says on its
   * retained row (#371).
   *
   * It is the whole of the page's choice. The app holds the loaded railroad
   * and hands the documents back (ADR-0038), so this says which and the app
   * reads it from the store. The settings dialog asks on `railroad_wanted` and
   * is answered here or not at all: what a person pressed never loads anything
   * by itself (ADR-0060). The trains come from the app, which has the loaded
   * railroad read them off the store — what stock there is to place, which no
   * topic carries (ADR-0039, #758). Everything else comes off the bus:
   * placement, locks and live requests off the dispatcher's retained picture,
   * facing off the scheduler's (ADR-0032, ADR-0036).
   */
  private named(railroad: string): void {
    if (railroad === "") {
      // No railroad loaded (#727): nothing to join, so the session goes and what is said instead is that none is.
      if (this.nameless) return;
      this.leave();
      this.nameless = true;
      this.settle();
      this.hooks.named("");
      this.hooks.notify();
      return;
    }
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
    this.settle();
    this.hooks.named(railroad);
    this.hooks.notify();
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
        // A drain somebody abandoned — this page's GO or another's — and the
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
        // (ADR-0062). A run that never drains leaves the railroad powered
        // and the button saying it is still waiting.
        this.cut();
      }
    }
    this.changed();
  }

  // --- the presses ----------------------------------------------------------

  /**
   * Hold the run, or release it: one `run_wanted` naming where it should
   * stand (ADR-0037). The app presses it on the rail, and the dispatcher's
   * answer comes back on `state/run` and redraws the button.
   *
   * Releasing with disputes outstanding is allowed — the person decides, not
   * the check — and the session says what is still disputed at the moment of
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
    this.changed();
  }

  /**
   * ON, STOP or OFF, pressed on the band: what the whole railroad's supply
   * should be doing (ADR-0074).
   *
   * **OFF is the drain trigger and never an immediate cut.** It asks the run
   * to drain — always, a held run included, because a held run can still be
   * moving — and waits for `state/run` to read `held` with nothing moving; an
   * abrupt `off` would leave no point position trustworthy and strand
   * whatever was mid-transit. `layout` refuses an `off` it should not apply
   * ([ADR-0062](../../../docs/adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)),
   * so this wait is the person's view of the drain rather than the only
   * guard; the page still does not send `off` blindly.
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
    } else {
      this.draining = false;
      this.send(powerWanted(power));
    }
    this.changed();
  }

  /**
   * A railroad chosen in the settings dialog: one `railroad_wanted` naming it
   * ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
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
   * ([#207](https://github.com/rails49/control/issues/207)). `layout` answers
   * by publishing `state/mode`, and the throttle reads who is driving off that
   * rather than off its own press (ADR-0035).
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
   *  `reversal_wanted` the run view's menu writes, the scheduler flipping
   *  the facing and nothing moving (ADR-0019). */
  pressReversal(train: string): void {
    this.send(reversal(train));
  }

  /** One frame, published on its own topic: the presses above, and the
   *  gestures the run view composes. `connected` and not merely a client:
   *  MQTT.js queues a publish made while it is reconnecting, and a gesture
   *  nobody heard must not look like one that landed. */
  send(frame: Frame): void {
    if (this.client === null || !this.connected) return;
    this.client.publish(frame.topic, JSON.stringify(frame.payload));
  }

  // --- what it answers ------------------------------------------------------

  /** The trains the railroad owns, as far as a view shows them: none with no
   *  session joined, as `leave` makes it, a page that has left a session
   *  having nothing of it to place or drive. */
  get owned(): Record<string, TrainDoc> {
    return this.session === null ? {} : this.trains;
  }

  /**
   * The trains the run has on the layout, and where each stands
   * (model/panel.ts). Worked out afresh on each call, being the last frame's
   * answer like everything else the picture says.
   *
   * Nothing, with no session joined, as the run's value and the supply's are.
   * `leave` keeps the model so that rejoining does not flash, but a page that
   * has left a session is being told nothing — and what this answers guards
   * the stock view's lengths, which must not outlive the knowledge they rest
   * on: a page reloaded guards nothing, and a page that has left is in the
   * same position.
   */
  get standing(): Placed[] {
    if (this.session === null) return [];
    return this.panel?.placed() ?? [];
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
    this.released = null;
    this.wasRunning = false;
    this.held = null;
    // A session going away takes the wait with it: the run whose drain was
    // being watched is no longer being reported on, and a cut fired at the
    // next session's first `held` would be this one's press arriving late.
    this.draining = false;
    this.session = null;
    this.nameless = false;
  }

  /** What moved, worked out and told. */
  private changed(): void {
    this.settle();
    this.hooks.notify();
  }

  /** `status` and `cabs` brought up to date, each kept as the same object
   *  where nothing it says has moved: the app holds what it is told, so a new
   *  object on a frame that changed nothing would redraw the whole page on
   *  every event the bus carries. */
  private settle(): void {
    const joined = this.session !== null;
    const model = joined ? this.panel : null;
    const now: RunStatus = {
      joined,
      railroad: this.nameless ? "" : this.session,
      linked: this.connected,
      run: model?.run ?? null,
      power: model?.power ?? null,
      draining: this.draining,
      trouble: this.trouble,
      // Nothing, with no session joined: it is the hardware's report on the
      // railroad this page is watching, as the supply's own reading is, and a
      // page that has left a session is being told nothing.
      fault: model?.fault ?? null,
      placed: this.standing.map(({ train }) => train),
    };
    if (!sameStatus(this.status, now)) this.status = now;
    const driving = this.driving;
    const written = JSON.stringify(driving);
    if (written !== this.saidCabs) {
      this.saidCabs = written;
      this.cabs = driving;
    }
  }

  /**
   * What the throttle view draws: one cab per train the railroad has placed
   * (`model/throttle.ts`, ui/THROTTLE.md).
   *
   * Worked out here because everything it is made of is here — the run's
   * picture, `layout`'s modes, the scheduler's facing, the dispatcher's
   * aspects and the railroad's roster. Nothing of the throttle's own is in
   * it: which train a person picked and where they have put the lever are
   * theirs, and live in the view with the pointer.
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
      stock: this.owned,
    });
  }
}

/** Whether two statuses say the same thing, field by field. */
function sameStatus(was: RunStatus, now: RunStatus): boolean {
  return (
    was.joined === now.joined &&
    was.railroad === now.railroad &&
    was.linked === now.linked &&
    was.run === now.run &&
    was.power === now.power &&
    was.draining === now.draining &&
    was.trouble === now.trouble &&
    was.fault === now.fault &&
    same(was.placed, now.placed)
  );
}

/** Whether two lists of placed trains say the same thing. A list is built
 *  afresh on every frame. */
function same(was: readonly string[], now: readonly string[]): boolean {
  return was.length === now.length && was.every((train, at) => train === now[at]);
}
