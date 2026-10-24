/**
 * The page's one connection to the broker, and everything that follows from
 * it (#756): the railroad the broker's row names, the run's picture the bus
 * feeds, power and the driving mode.
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
import { Panel, type Placed } from "./panel.js";
import { RETRY_MS, type Review, type TrainDoc } from "./store.js";
import { cabs, type Cab } from "./throttle.js";
import { WIDGET_PREFIX, type WidgetPress } from "./widgets.js";
import {
  drivingWanted,
  functionWanted,
  Live,
  powerWanted,
  railroadWanted,
  takeWanted,
  throttleAlive,
  throttleWanted,
  type DrivingMode,
  type Frame,
  type Power,
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
   *  (#371) and `""` where it says it runs none (#727). The app reads it to
   *  know whether the open drawing is the loaded railroad, whose save names
   *  it again and which ON saves first (`model/commands.ts`, ADR-0085). */
  railroad: string | null;
  linked: boolean;
  /** Power, `on`, `draining` or `off`, `null` while no session is joined or
   *  before the layout has said (ADR-0078), whether or not the drawing
   *  is valid. The band's power control draws it. */
  power: Power | null;
  /** The railroad's driving mode, `null` while no session is joined or before
   *  the layout has said (ADR-0079). The band's driving control draws it. */
  driving: DrivingMode | null;
  /** Whether the apps built anything from the railroad the row names:
   *  `false` where the row says `built: false`, its drawing not being a valid
   *  drawing, and `true` otherwise — a row with no `built`, a row naming
   *  none, and no row yet among them (BUS.md). The railroad stays named
   *  either way, and the app opens its drawing in the Edit view to be fixed
   *  ([ADR-0085](../../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
   *  decision 4). */
  built: boolean;
  /** Whether `tc49/dispatch/state/allocation` has arrived since the row
   *  last named another railroad: the dispatcher built on the one it names
   *  and said so. The settings dialog waits for it before it closes on a
   *  pick (#902); a railroad not built has no dispatcher on it and never
   *  reads `true`. */
  allocated: boolean;
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
  power: null,
  driving: null,
  built: true,
  allocated: false,
  trouble: null,
  fault: null,
  placed: [],
};

/**
 * The client, as far as a session uses one: the five calls `mqtt.connect`
 * hands back, and the same five `test/support/broker.ts` stands for. Any more
 * of MQTT.js here would be surface a suite's broker has to fake. `retain` is
 * asked for by a toggle's press alone (ADR-0087).
 */
export interface Client {
  on(event: "connect" | "close" | "error", listener: () => void): unknown;
  on(event: "message", listener: (topic: string, payload: Uint8Array) => void): unknown;
  subscribe(filter: string): unknown;
  publish(topic: string, payload: string, options?: { retain: boolean }): unknown;
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

/** How often a throttle holding a train says it is still there. `layout`
 *  releases the trains of a throttle it has not heard for 5 s, so a phone
 *  gone to sleep does not leave a train running
 *  ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)). */
export const ALIVE_MS = 1000;

/** A throttle id: a random string the page mints when it opens, naming the
 *  throttle that holds a train (BUS.md, `take_wanted`). From
 *  `getRandomValues` and not `randomUUID`, which a page served over plain
 *  HTTP on the layout's own network does not have. */
export function minted(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

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

  /** The widget rows, `tc49/ui/state/…`, by their whole topic, each payload
   *  as it arrived (ADR-0087): the run view's text and toggles read them. A
   *  new map whenever one moves. Not the panel model's: a widget's topic
   *  names no railroad, and its rows are kept whichever one is joined. */
  widgetRows: ReadonlyMap<string, string> = new Map();


  /** The railroad the broker says it runs, `null` while it has not said —
   *  before the connection lands, and again after it has gone (#371). */
  private session: string | null = null;
  /** Whether the row names no railroad, `""`: there is no session to join,
   *  but the broker has said, which is not the same as not having said. */
  private nameless = false;
  /** The railroad a `railroad_wanted` pressed while the broker had gone was
   *  to name, `null` while no press is owed (#803). The last press wins. */
  private owed: string | null = null;
  /** The railroad ON is waiting to see built, and the stamp of the row last
   *  heard when its save landed — `saving` while the save is still out —
   *  `null` while ON waits for nothing (ADR-0085, decision 2). */
  private building: { railroad: string; after: number | null; saving: boolean } | null =
    null;
  /** The stamp on the last `tc49/layout/state/railroad` row, `null` before
   *  one or where it carried none. */
  private stamped: number | null = null;
  /** Whether the last `tc49/layout/state/railroad` row named a railroad and
   *  said nothing was built from it. */
  private unbuilt = false;
  /** Whether `state/allocation` has arrived since the row named the
   *  railroad joined (`RunStatus.allocated`). */
  private allocated = false;
  /** Track power as `state/power` last said it, read whether or not a panel
   *  model is built: a page whose drawing is invalid builds none, and
   *  still has to know whether it may save (ADR-0085). */
  private supplied: Power | null = null;
  private connected = false;
  private trouble: string | null = null;
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
  /** The timer saying `throttle_alive`, `null` while no throttle of this
   *  page holds a train. */
  private alive: ReturnType<typeof setInterval> | null = null;
  /** This page's throttle ids, by the panel slot each was minted for, in
   *  the order they were minted (`throttleFor`). */
  private readonly throttles = new Map<number, string>();

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
   * drawing's name changes or the drawing turns valid or invalid. A railroad
   * whose drawing is invalid has no layout to build from, so nothing is painted
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
      this.panel = new Panel(layout, explain, drawing!.wires);
      this.built = name;
      for (const event of this.held ?? []) this.applied(event);
      this.held = null;
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
      this.widgetRows = new Map();
      this.supplied = null;
      this.allocated = false;
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
      // the page holds no session at all: the roster empties, and the picture
      // the last frame left stays on screen with nothing to gesture at. The
      // drawing stays frozen: it is still open with no railroad heard, and
      // the track may well have power (#792).
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
      this.allocated = false;
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
    // Another railroad named under a joined one starts with nothing said
    // about power or the allocation, as its panel does; on a fresh
    // connection either row may have landed first, and is kept.
    if (this.session !== null) {
      this.supplied = null;
      this.allocated = false;
    }
    this.leave();
    this.session = railroad;
    this.held = early ?? [];
    this.settle();
    this.hooks.named(railroad);
    this.hooks.notify();
  }

  private heard(topic: string, payload: string): void {
    if (this.live === null) return;
    if (topic.startsWith(WIDGET_PREFIX)) {
      this.widgetRow(topic, payload);
      return;
    }
    const event = this.live.read(topic, payload);
    if (event === null) return;
    if (topic === RAILROAD) {
      const name = event["name"];
      if (typeof name !== "string") return;
      const at = event["at"];
      const built = event["built"] !== false;
      this.rebuilt(name, typeof at === "number" ? at : null, built);
      const unbuilt = name !== "" && !built;
      const turned = unbuilt !== this.unbuilt;
      this.unbuilt = unbuilt;
      this.named(name);
      // The same railroad named again joins nothing, so what the row says
      // about its build is told here.
      if (turned) this.changed();
      return;
    }
    if (event.event === "power") {
      const { power } = event as unknown as { power?: unknown };
      this.supplied = power === "on" || power === "draining" ? power : "off";
    }
    const allocated = event.event === "allocation" && !this.allocated;
    if (allocated) this.allocated = true;
    if (this.panel === null) {
      if (this.held !== null && this.held.length < HELD) this.held.push(event);
      if (event.event === "power" || allocated) this.changed();
      return;
    }
    this.applied(event);
    this.changed();
  }

  /**
   * A message on a widget's topic, read before anything is read as JSON: a
   * widget payload is raw (ADR-0087 decision 4, #929), so one that is not
   * JSON is neither an error nor dropped, and touches no other row. A state
   * row is kept, an empty one being a row the broker no longer holds; a
   * button's press, this page's own coming back among them, is an event and
   * nothing here reads it.
   */
  private widgetRow(topic: string, payload: string): void {
    if (!topic.startsWith(`${WIDGET_PREFIX}state/`)) return;
    if (this.widgetRows.get(topic) === payload) return;
    const rows = new Map(this.widgetRows);
    if (payload === "") rows.delete(topic);
    else rows.set(topic, payload);
    this.widgetRows = rows;
    this.hooks.notify();
  }

  /** One event applied to the model. */
  private applied(event: TraceEvent): void {
    this.panel!.apply(event);
  }

  // --- the presses ----------------------------------------------------------

  /**
   * Power asked for on the band: `on`, `draining` or `off`, one
   * `power_wanted` naming where power should stand (ADR-0078). What a press
   * on the control asks for is `asked` in `model/commands.ts`.
   *
   * **The drain is `layout`'s.** The page asks for `draining` and waits for
   * nothing: `layout` switches the supply off once nothing is moving, and
   * what the band then shows is `state/power` coming back (ADR-0035). The
   * emergency stop is `off` at once, which `layout` applies whatever is
   * moving.
   */
  pressPower(power: Power): void {
    this.building = null;
    this.send(powerWanted(power));
  }

  /**
   * ON pressed over a drawing being saved: `power_wanted` `on` sent once the
   * row comes back naming `railroad` from a build after the save landed
   * ([ADR-0085](../../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
   * decision 2). The power comes on over what the apps built from what was
   * saved, never over the build before it. Naming the railroad again is the
   * save's own (`Railroad`, model/railroad.ts), so nothing is named here.
   *
   * ON is waiting from the call on. A save that answers `false` sends
   * nothing. Nor does a row saying `built: false`, which built nothing: a
   * drawing that is not a valid drawing runs no train. Nor is anything sent
   * where a row names another railroad first, or another power press comes
   * first, while the write is out or the build has not arrived — a STOP while
   * waiting is a person changing their mind.
   */
  pressOnSaved(railroad: string, saved: Promise<boolean>): void {
    const waiting = { railroad, after: null as number | null, saving: true };
    this.building = waiting;
    void saved
      .catch(() => false)
      .then((landed) => {
        if (this.building !== waiting) return;
        if (!landed) {
          this.building = null;
          return;
        }
        waiting.after = this.stamped;
        waiting.saving = false;
      });
  }

  /** A row naming `railroad`, stamped `at`, saying whether anything was
   *  built from it: what ON may be waiting for. A row with a stamp no later
   *  than the one held at the press is the build before it, replayed. */
  private rebuilt(railroad: string, at: number | null, built: boolean): void {
    const waiting = this.building;
    this.stamped = at;
    if (waiting === null || waiting.saving) return;
    if (railroad !== waiting.railroad) {
      this.building = null;
      return;
    }
    if (at !== null && waiting.after !== null && at <= waiting.after) return;
    this.building = null;
    if (built) this.pressPower("on");
  }

  /**
   * The railroad's driving mode asked for on the band: one `driving_wanted`
   * naming it
   * ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
   * `layout` answers on `state/driving`, which is what the control draws.
   */
  pressDriving(driving: DrivingMode): void {
    this.send(drivingWanted(driving));
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
   *
   * The one press not dropped while the broker has gone: a Save that lands
   * then names the railroad nowhere else, the row coming back naming the same
   * one, so the request is owed and `settle` sends it once the row names that
   * railroad again and power reads off, the only power `layout` builds under.
   * A row naming another railroad, or none, drops it (#803).
   */
  pressRailroad(railroad: string): void {
    if (this.client === null || !this.connected) {
      this.owed = railroad;
      return;
    }
    this.owed = null;
    this.send(railroadWanted(railroad));
  }

  /**
   * Take a train in a throttle: one `take_wanted` naming the train and the
   * id of the panel it was pressed in (`throttleFor`,
   * [ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
   * `layout` answers by publishing `state/taken`, and the throttle reads who
   * holds the train off that rather than off its own press (ADR-0035).
   */
  pressTake(train: string, throttle: string): void {
    this.send(takeWanted(train, throttle));
  }

  /** Release a train: one `take_wanted` with `null`, which releases it
   *  whoever holds it — this throttle giving it back and the force release
   *  of one held elsewhere are the same frame (BUS.md). */
  pressRelease(train: string): void {
    this.send(takeWanted(train, null));
  }

  /** A function button pressed: one `function_wanted` naming the train, the
   *  panel's throttle id, the function by its catalogue name and whether to switch it
   *  on. `layout` answers on `state/functions`, which the button reads, and
   *  drops a press from a throttle not holding the train (#849). */
  pressFunction(train: string, throttle: string, fn: string, on: boolean): void {
    this.send(functionWanted(train, throttle, fn, on));
  }

  /** The throttle turned: one `throttle_wanted` carrying the number the lever
   *  shows and the panel's throttle id. One signed speed for the train — which
   *  locomotive it reaches, and which way round that one stands, is
   *  `layout`'s (GLOSSARY.md, **Throttle**). */
  pressThrottle(train: string, speed: number, throttle: string): void {
    this.send(throttleWanted(train, speed, throttle));
  }

  /** One frame, published on its own topic: the presses above, and the
   *  gestures the run view composes. `connected` and not merely a client:
   *  MQTT.js queues a publish made while it is reconnecting, and a gesture
   *  nobody heard must not look like one that landed — it is dropped, all
   *  but a `pressRailroad`, which is owed instead (#803). */
  send(frame: Frame): void {
    if (this.client === null || !this.connected) return;
    this.client.publish(frame.topic, JSON.stringify(frame.payload));
  }

  /**
   * A widget pressed in the run view: its payload published raw, as typed,
   * and not through `JSON.stringify` — a toggle's retained, a button's not
   * (`widgetPress`, ADR-0087). Whatever the track power: a widget is not the
   * railroad's. Dropped while the broker is not answering, as `send` drops a
   * gesture.
   */
  pressWidget(press: WidgetPress): void {
    if (this.client === null || !this.connected) return;
    this.client.publish(press.topic, press.payload, { retain: press.retain });
  }

  // --- what it answers ------------------------------------------------------

  /**
   * The throttle id of the throttle view's panel `slot`: minted on the first
   * call for that slot and kept for the life of the page, so every take,
   * speed, function and alive frame from one panel names the same id and
   * each panel's differs (ADR-0089). A train held by the panel beside it is
   * held by another throttle.
   */
  throttleFor(slot: number): string {
    let id = this.throttles.get(slot);
    if (id === undefined) {
      id = minted();
      this.throttles.set(slot, id);
    }
    return id;
  }

  /** Whether `throttle` is one this page minted: what tells the app a train
   *  is held here, for the screen's wake lock. */
  ours(throttle: string | null): boolean {
    return throttle !== null && [...this.throttles.values()].includes(throttle);
  }

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

  /** The session goes: the broker has stopped answering, or it has named
   *  another railroad. What the model holds is kept — a page getting back in
   *  must not flash — and everything the last session put on screen of its own
   *  goes. */
  private leave(): void {
    this.held = null;
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
    const power = joined ? (model?.power ?? this.supplied) : null;
    this.repay(power);
    const now: RunStatus = {
      joined,
      railroad: this.nameless ? "" : this.session,
      linked: this.connected,
      power,
      driving: model?.driving ?? null,
      built: !this.unbuilt,
      allocated: joined && this.allocated,
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
    this.beat(this.holding.length > 0);
  }

  /** This page's throttle ids that `state/taken` names for a train on the
   *  layout, in the order they were minted, each once. */
  private get holding(): string[] {
    const named = new Set(this.cabs.map(({ holder }) => holder));
    return [...this.throttles.values()].filter((id) => named.has(id));
  }

  /** `throttle_alive` once every `ALIVE_MS` for each of this page's ids that
   *  `state/taken` names for a train on the layout, and silence while it
   *  names none. Started on the row and not on the press: `layout` counts
   *  the take itself as hearing from that throttle. Each tick reads the ids
   *  afresh, so an id the row drops goes quiet and the others go on. */
  private beat(holding: boolean): void {
    if (holding && this.alive === null) {
      this.alive = setInterval(() => {
        for (const id of this.holding) this.send(throttleAlive(id));
      }, ALIVE_MS);
    } else if (!holding && this.alive !== null) {
      clearInterval(this.alive);
      this.alive = null;
    }
  }

  /** The press owed since the broker went, sent where the row names its
   *  railroad again and power reads off, and dropped where the row names
   *  another or none. Power on or draining, or not yet replayed after the
   *  reconnect (`panel.reset()`), keeps it waiting: `layout` would drop the
   *  request. Cleared before it is sent, so it goes once. */
  private repay(power: Power | null): void {
    const owed = this.owed;
    if (owed === null || !this.connected) return;
    if (this.nameless || (this.session !== null && this.session !== owed)) {
      this.owed = null;
    } else if (this.session === owed && power === "off") {
      this.owed = null;
      this.send(railroadWanted(owed));
    }
  }

  /**
   * What the throttle view draws: one cab per train the railroad has placed
   * (`model/throttle.ts`, ui/THROTTLE.md).
   *
   * Worked out here because everything it is made of is here — the run's
   * picture, which throttle `layout` says holds each train, the moves
   * granted, the scheduler's facing, the dispatcher's aspects and the
   * railroad's roster. Where a person has put the slider is theirs, and lives
   * in the view with the pointer.
   */
  private get driving(): Cab[] {
    const model = this.panel;
    if (model === null || this.session === null) return [];
    const placed = model.placed();
    return cabs({
      placed,
      taken: model.taken(),
      functions: model.functions(),
      granted: model.granted(),
      noses: model.noses(),
      aspects: model.aspects(),
      ahead: model.ahead(),
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
    was.power === now.power &&
    was.driving === now.driving &&
    was.built === now.built &&
    was.allocated === now.allocated &&
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
