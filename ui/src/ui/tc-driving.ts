/**
 * One train's driving controls on the throttle view (ui/THROTTLE.md), laid
 * out as `docs/ui/images/throttle-mockup.html` draws a held panel
 * ([#968](https://github.com/rails49/control/issues/968)): the train's
 * picture across the top, and below it two columns — the clock, the blocks
 * the train is at and heading for, the signal it reads and its functions on
 * the left, and the speed, the slider and the one button under it on the
 * right, where a right thumb is. The same layout at every width a panel is
 * drawn at, 360–440 px (ADR-0089).
 *
 * `tc-throttle` draws one in each panel whose throttle holds a train
 * (ADR-0089), and each owns its own train's slider and reverser: they are the
 * person's and not the bus's, so they live with the pointer that moves them.
 * Every press names this panel's train and its throttle id and no other, and
 * goes to the app as an event, exactly as the band's power presses do. The
 * picture is the press that opens the panel's train selector
 * (`tc-train-picker`), which gives the train back and takes another:
 * `selector-wanted`, to the panel and not the app (#967).
 *
 * **The speed is in the train's frame.** The slider runs 0 to 1 and the
 * reverser gives it its sign: Forward nose first, `+`, Reverse tail first,
 * `−` (GLOSSARY.md, **Reverser**). `layout` composes the sign each locomotive
 * is given from the train's facing and the way round its car is coupled — so
 * one slider drives a top-and-tail set and this sends one number and never a
 * direction for a locomotive (GLOSSARY.md, **Throttle**).
 */

import { LitElement, html, nothing, svg } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";

import { watchPicture, type Watching } from "../model/picture.js";
import type { Ahead } from "../model/panel.js";
import { photoUrl, pictureUrl, RETRY_MS } from "../model/store.js";
import { driveRefusal, type Cab, type CabFunction } from "../model/throttle.js";
import type { Aspect } from "../render/artwork.js";
import type { Power } from "../model/trace.js";
import "./tc-clock.js";
import { drivingStyles, TRACK_PAD_PX } from "./tc-driving.styles.js";

/** The slider moved: the train it is about, the speed it now asks for,
 *  signed by the reverser, and the panel's throttle id. The view writes
 *  nothing itself — the session is the app's, and the app carries the press
 *  there as it carries the band's (ADR-0074's path, ui/THROTTLE.md). */
export interface ThrottleWanted {
  train: string;
  speed: number;
  throttle: string;
}

/** A function button pressed: the train, the panel's throttle id, the
 *  function by its catalogue name, and `on` the opposite of what the button
 *  shows — the one the app carries to `Session.pressFunction`. */
export interface FunctionWanted {
  train: string;
  throttle: string;
  function: string;
  on: boolean;
}

/** How many steps the slider divides its travel into: hundredths, the whole
 *  percentage a person reads, so the number on screen is what goes on the
 *  bus. */
const STEPS = 100;

/** What an arrow key moves it by: one step. */
const STEP = 1 / STEPS;

/** What PageUp and PageDown move it by. */
const PAGE = 0.1;

/** The tick marks up the track, one every 5 %: 0 through 20. */
const TICKS = Array.from({ length: 21 }, (_, at) => at);

/** The signal's three lamps, top to bottom, in the Swiss order
 *  (docs/ui/EDITOR.md): each with its height on the head and the colour it
 *  is lit in. The colours are a lamp's and not the page's, so they are the
 *  same in either theme. */
const LAMPS = [
  { lamp: "green", y: 32, colour: "#22c55e" },
  { lamp: "red", y: 68, colour: "#ef4444" },
  { lamp: "amber", y: 104, colour: "#f59e0b" },
] as const;

/** Which lamps each aspect lights. */
const LIT: Record<Aspect, readonly string[]> = {
  stop: ["red"],
  caution: ["green", "amber"],
  clear: ["green"],
};

/** A train seen from the front, drawn where it has no photo. */
const TRAIN = svg`<svg class="icon" viewBox="0 0 64 64" aria-hidden="true" fill="none"
    stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
  <rect x="15" y="6" width="34" height="40" rx="9" />
  <rect x="21" y="12" width="22" height="13" rx="3" />
  <circle cx="24" cy="36" r="2.4" fill="currentColor" />
  <circle cx="40" cy="36" r="2.4" fill="currentColor" />
  <path d="M22 46 13 58M42 46l9 12M17 53h30" />
</svg>`;

/** ▶, ◀ and the stop square, each 24 units, drawn in the text's colour. */
const FORWARD = svg`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5 20 12 7 19.5Z" fill="currentColor" /></svg>`;
const REVERSE = svg`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 4.5 4 12l13 7.5Z" fill="currentColor" /></svg>`;
const SQUARE = svg`<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2.5" fill="currentColor" /></svg>`;

/** Two arrows, one each way: the picture changes the train. */
const SWAP = svg`<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 7h12l-3-3M17 13H5l3 3" fill="none"
    stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" /></svg>`;

/** The keys that hold a focused momentary button, as they press any
 *  button. */
const HOLD_KEYS: ReadonlySet<string> = new Set([" ", "Enter"]);

/** A drag on the track under way: where the pointer went down, the value it
 *  stood at then, and the pixels the whole of its travel spans. */
interface Drag {
  pointer: number;
  y: number;
  from: number;
  span: number;
}

@customElement("tc-driving")
export class TcDriving extends LitElement {
  static override styles = drivingStyles;

  /** The train this panel drives, as the session last answered for it:
   *  one `state/taken` names this panel's throttle for. Read afresh on every
   *  frame — the bus moves under a person holding a slider. */
  @property({ attribute: false }) cab: Cab | null = null;

  /** The id of the panel's throttle (`Session.throttleFor`), which every
   *  speed and function press names. */
  @property() throttle = "";

  /** Whether a train may move at all, `null` while no session is joined or
   *  before the layout has said (ADR-0041). The controls are dead while it
   *  is anything but `on`, and say which. */
  @property() power: Power | null = null;

  /** Whether a session is joined and answering. A gesture into a socket that
   *  is not there is swallowed, so the controls say so instead. */
  @property({ type: Boolean }) linked = false;

  /** Whether the throttle is the view on screen. The camera car's picture is
   *  drawn only while it is: a view switched away holds no connection to the
   *  camera app. */
  @property({ type: Boolean }) current = false;

  /** The fast clock's time of day, fast seconds since midnight, as
   *  `state/clock` last said it; `null` with no railroad loaded or the
   *  broker not answering (ADR-0090). The station clock draws it. */
  @property({ attribute: false }) clock: number | null = null;

  /** The loaded railroad's name, which the camera app's route is under;
   *  `null` or `""` while none is loaded. */
  @property() railroad: string | null = null;

  /** Where the slider stands, as the person left it: 0 through 1. It is the
   *  panel's own and not the bus's — nothing publishes a throttle's position
   *  back — so it is what this shows and, signed, what it last sent. */
  @state() private slider = 0;

  /** The reverser: Reverse where `true`, Forward where not. Like the slider
   *  it is the person's, and it sends nothing when it moves (ADR-0084). */
  @state() private reverse = false;

  /** The models whose photo did not load, drawn by the train's name. */
  @state() private unseen: ReadonlySet<string> = new Set();

  /** How many times the camera car's picture has been asked for again since
   *  it was first drawn: the `try` that makes each a new request. */
  @state() private attempt = 0;

  /** Whether the picture failed and is waiting `RETRY_MS` to be asked for
   *  again, the thumbnail showing meanwhile. */
  @state() private failed = false;

  /** The timer that asks for it again, `null` while none is set. */
  private retry: ReturnType<typeof setTimeout> | null = null;

  /** The newest frame of the picture, as an object URL; `null` until one
   *  has come, and while the picture is not drawn. */
  @state() private frame: string | null = null;

  /** The stream being read, `null` while none is. */
  private reading: Watching | null = null;

  /** The drag on the track under way, `null` while there is none. */
  private drag: Drag | null = null;

  /** The momentary functions whose button is held now: the train of each,
   *  by the function's name. */
  private held = new Map<string, string>();

  /** The root this panel was drawn in, where an off it says as it is removed
   *  still reaches the page: the panel itself is no longer in it then. */
  private home: Node | null = null;

  @query(".track") private track!: HTMLElement | null;

  override willUpdate(changed: Map<string, unknown>): void {
    // The picture no longer wanted: no retry waits, and the next time it is
    // wanted it is asked for afresh.
    if (this.watched === null) this.unwatch();
    // The track is off: nothing is moving, so neither is the slider.
    if (changed.has("power") && this.power === "off") this.slider = 0;
    if (!changed.has("cab")) return;
    const cab = this.cab;
    const was = changed.get("cab") as Cab | null | undefined;
    // A panel draws these afresh for each take, so its train does not change
    // under it; were it to, the slider starts at rest and the reverser at
    // Forward, a position carried over being a speed this one was never
    // driven at.
    if (was?.train !== cab?.train) {
      this.unwatch();
      this.slider = 0;
      this.reverse = false;
      return;
    }
    // A granted move ended at its sensor: `layout` has written `0.0`, and
    // the slider shows the train standing. A frame that only leaves a train
    // with no move, where it had none, ends nothing.
    if (cab !== null && was?.granted === true && !cab.granted) this.slider = 0;
  }

  /** Read the stream the picture is wanted from, and stop reading any
   *  other. In `update` rather than `willUpdate`, so it sees the `attempt`
   *  and `failed` that `willUpdate` has just set. */
  override update(changed: Map<string, unknown>): void {
    this.follow(this.failed ? null : this.watched);
    super.update(changed);
  }

  override connectedCallback(): void {
    super.connectedCallback();
    this.home = this.getRootNode();
    document.addEventListener("visibilitychange", this.hiding);
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener("visibilitychange", this.hiding);
    this.unwatch();
    this.follow(null);
    this.lettingAll();
    this.home = null;
  }

  /** The page hidden: no key or pointer coming up reaches it, so every hold
   *  ends now. */
  private readonly hiding = (): void => {
    if (document.visibilityState === "hidden") this.lettingAll();
  };

  override render() {
    const cab = this.cab;
    return cab === null ? nothing : this.cabinet(cab);
  }

  /** Whether a gesture can be sent at all: a session that is answering, over
   *  rails a train may move on. The view says which is missing, and every
   *  control that would write is dead while it is (ui/THROTTLE.md). */
  private get live(): boolean {
    return this.still === null;
  }

  /** Why nothing can be driven, or `null` where something can
   *  (`model/throttle.ts`). */
  private get still(): string | null {
    return driveRefusal(this.linked, this.power);
  }

  private cabinet(cab: Cab) {
    const still = this.still;
    return html`
      <button
        class="view"
        aria-label="Choose a train"
        @click=${() => this.say<null>("selector-wanted", null)}
      >
        ${this.frame === null ? this.thumbnail(cab) : this.picture()}
        ${this.frame === null
          ? nothing
          : html`<span class="chip live"><i></i>LIVE</span>`}
        ${this.frame === null && this.drawnAsName(cab)
          ? nothing
          : html`<span class="chip title">${cab.train}</span>`}
        <span class="chip trains">${SWAP}Trains</span>
        ${cab.addresses.length === 0
          ? nothing
          : html`<span class="chip addresses"
              >${cab.addresses.map((one) => `#${one}`).join(" ")}</span
            >`}
      </button>
      <section class=${still === null ? "lower" : "lower dead"}>
        <div class="left">
          <div class="readout">
            <tc-clock .time=${this.clock}></tc-clock>
            ${this.blocks(cab)} ${this.signal(cab)}
          </div>
          ${this.functions(cab)}
        </div>
        <div class="right">${this.driving(cab)}</div>
        ${still === null ? nothing : html`<p class="still">${still}</p>`}
      </section>
    `;
  }

  /** Whether the train is drawn as its icon and name rather than a photo:
   *  the name is under the icon then, and not laid over it a second time. */
  private drawnAsName(cab: Cab): boolean {
    return cab.locomotive === null || this.unseen.has(cab.locomotive);
  }

  /** The model photo of the train's first locomotive, or a train and its
   *  name where it has none, the roster does not have it, or the photo does
   *  not load — a model with no photo filed answers 404, as the stock screen
   *  finds. */
  private thumbnail(cab: Cab) {
    const model = cab.locomotive;
    if (model === null || this.unseen.has(model)) {
      return html`<span class="thumbnail name">${TRAIN}<span>${cab.train}</span></span>`;
    }
    return html`<img
      class="thumbnail"
      src=${photoUrl(model)}
      alt=${cab.train}
      @error=${() => (this.unseen = new Set([...this.unseen, model]))}
    />`;
  }

  /**
   * The camera car's live picture, in the thumbnail's place, while all three
   * hold: this view is current, `state/taken` names this panel's throttle
   * for the train, and the train
   * carries a camera. Otherwise the page holds no connection to the camera
   * app (ui/THROTTLE.md). A stream that fails, ends or stalls takes it away
   * (`model/picture.ts`), and the thumbnail shows until it is asked for again
   * `RETRY_MS` later under a new `try`. Called once a frame has come.
   */
  private picture() {
    return html`<img class="picture" src=${this.frame} alt="" />`;
  }

  /** Read the stream at `url`, or none where it is `null`, dropping the
   *  frame of any other. */
  private follow(url: string | null): void {
    if (url === (this.reading?.url ?? null)) return;
    this.reading?.stop();
    this.show(null);
    this.reading =
      url === null
        ? null
        : watchPicture(
            url,
            (jpeg) => this.show(URL.createObjectURL(jpeg)),
            () => this.lost(),
          );
  }

  /** Draw `frame`, letting go of the one before it. */
  private show(frame: string | null): void {
    if (this.frame !== null) URL.revokeObjectURL(this.frame);
    this.frame = frame;
  }

  /** The camera app's route for the train held, `null` where the picture is
   *  not to be drawn. Track power does not matter: a train standing dark is
   *  still worth seeing. Controls taken out of the page still update, so
   *  they ask for nothing. */
  private get watched(): string | null {
    const cab = this.cab;
    if (
      !this.isConnected ||
      !this.current ||
      cab === null ||
      cab.holder !== this.throttle ||
      !cab.camera ||
      !this.railroad
    ) {
      return null;
    }
    return pictureUrl(this.railroad, cab.train, this.attempt);
  }

  /** The stream failed, ended or stalled: the thumbnail shows, and the
   *  picture is asked for again after `RETRY_MS`, while it is still wanted. */
  private lost(): void {
    this.failed = true;
    if (this.retry !== null) clearTimeout(this.retry);
    this.retry = setTimeout(() => {
      this.retry = null;
      this.attempt += 1;
      this.failed = false;
    }, RETRY_MS);
  }

  /** Stop watching: no retry pending, and the next picture starts afresh. */
  private unwatch(): void {
    if (this.retry !== null) clearTimeout(this.retry);
    this.retry = null;
    this.failed = false;
    this.attempt = 0;
  }

  /**
   * Where the train is and where it is going: *at* the block it stands in,
   * *next* the first block of the road ahead and *to* the last, the two
   * coloured as the run view lights a route — green where the lock is held,
   * cyan where the route is chosen. A train crossing a transit stands in no
   * block, and says so; with no road ahead, *next* and *to* read *—*.
   */
  private blocks(cab: Cab) {
    const next = cab.ahead[0];
    const to = cab.ahead.at(-1);
    const road = (label: string, block: Ahead | undefined) => html`
      <span class="label">${label}</span>
      ${block === undefined
        ? html`<span class=${`block ${label} none`}>—</span>`
        : html`<span class=${`block ${label} ${block.claim}`} title=${block.claim}
            >${block.block}</span
          >`}
    `;
    return html`<div class="blocks">
      ${cab.block === null
        ? html`<span class="label"></span
            ><span class="block at none">crossing a transit</span>`
        : html`<span class="label">at</span><span class="block at">${cab.block}</span>`}
      ${road("next", next)} ${road("to", to)}
    </div>`;
  }

  /**
   * The signal the train reads, as a three-lamp head: green at the top, red
   * in the middle, amber at the bottom (the Swiss order, docs/ui/EDITOR.md).
   * Stop lights red, caution green and amber, clear green, and no aspect
   * lights nothing. It is the aspect at the end the reverser points the
   * train to: the end its facing names for Forward, the block's other end
   * for Reverse (ADR-0025). Like the clock it is a picture of a thing on the
   * railroad, so the head and its lamps keep their colours in either theme;
   * the rim follows the page.
   */
  private signal(cab: Cab) {
    const aspect = this.reverse ? cab.tailAspect : cab.aspect;
    const lit = aspect === null ? [] : LIT[aspect];
    return html`<svg
      class="signal"
      viewBox="0 0 52 160"
      role="img"
      aria-label=${aspect === null ? "no signal ahead" : `signal ahead: ${aspect}`}
    >
      <rect class="mast" x="22" y="132" width="8" height="28" />
      <rect class="head" x="3" y="4" width="46" height="128" rx="17" fill="#0d0f12" />
      ${LAMPS.map(({ lamp, y, colour }) =>
        lit.includes(lamp)
          ? svg`<circle class=${`lamp ${lamp} lit`} cx="26" cy=${y} r="12.5" fill=${colour} />`
          : svg`<circle class=${`lamp ${lamp}`} cx="26" cy=${y} r="12.5" fill="#22262d" />`,
      )}
    </svg>`;
  }

  /**
   * What a person can switch on this train, by the names the catalogue gives
   * them (ADR-0045), in the order the roster lists them, down the left column
   * and then down the right, the left taking the odd one (#1031), every one
   * of them: where they do not fit, they scroll and nothing else does. A
   * train whose cars declare none shows none, which is most of the stock a
   * railroad owns.
   *
   * A latching one asks, at a press, for the opposite of what the button
   * shows. A momentary one asks for on as the pointer goes down and for off
   * as it comes up, is cancelled or is lost — the button captures it, so a
   * finger sliding off still ends the hold — and Space or Enter held on it
   * does the same, the key's repeat ignored
   * ([#981](https://github.com/rails49/control/issues/981)). A hold also
   * ends as the button loses focus, the page is hidden or the panel is
   * removed, and its end asks for off over dead rails too
   * ([#994](https://github.com/rails49/control/issues/994)). Either way the
   * button shows what `state/functions` says, `aria-pressed` where it is on
   * — it changes when `layout` says it switched it and not when it was
   * pressed ([#856](https://github.com/rails49/control/issues/856)). Live
   * whenever this throttle holds the train over live rails, granted move or
   * not, and otherwise drawn with their state and dead.
   */
  private functions(cab: Cab) {
    const half = Math.ceil(cab.functions.length / 2);
    return html`<div class="functions">
      <div class="column">
        ${cab.functions.slice(0, half).map((one) => this.function(cab, one))}
      </div>
      <div class="column">
        ${cab.functions.slice(half).map((one) => this.function(cab, one))}
      </div>
    </div>`;
  }

  private function(cab: Cab, one: CabFunction) {
    return one.mode === "momentary"
      ? html`
          <button
            class="function"
            aria-pressed=${one.on}
            ?disabled=${!this.live}
            @pointerdown=${(event: PointerEvent) => {
              (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
              this.holding(cab.train, one.name);
            }}
            @pointerup=${() => this.letting(cab.train, one.name)}
            @pointercancel=${() => this.letting(cab.train, one.name)}
            @lostpointercapture=${() => this.letting(cab.train, one.name)}
            @keydown=${(event: KeyboardEvent) => {
              if (!HOLD_KEYS.has(event.key)) return;
              event.preventDefault();
              if (!event.repeat) this.holding(cab.train, one.name);
            }}
            @keyup=${(event: KeyboardEvent) => {
              if (!HOLD_KEYS.has(event.key)) return;
              event.preventDefault();
              this.letting(cab.train, one.name);
            }}
            @blur=${() => this.letting(cab.train, one.name)}
          >
            ${one.name}
          </button>
        `
      : html`
          <button
            class="function"
            aria-pressed=${one.on}
            ?disabled=${!this.live}
            @click=${() => this.switching(cab.train, one.name, !one.on)}
          >
            ${one.name}
          </button>
        `;
  }

  /**
   * The speed, the slider and the button under it.
   *
   * The speed reads as a whole percentage of the train's maximum, with no
   * sign — which way the reverser is set is said under it. The slider runs
   * 0 at the bottom to 1 at the top in hundredths and is live whenever this
   * throttle holds the train over live rails, granted move or not (ADR-0081).
   * A drag on the thumb moves it by the distance the pointer travels over
   * the track's usable height, so a touch on the thumb does not move it; a
   * press anywhere else on the track puts it under the pointer, and a drag
   * from there follows the pointer (#996). The arrow keys move it a
   * hundredth and PageUp and PageDown a tenth.
   *
   * The button is two presses by where the slider is. Above 0 it is the
   * stop: the slider to 0 in one press, what a person reaches for when
   * something is wrong, the reverser left as it is. At 0 it is the reverser,
   * ▶ Forward or ◀ Reverse, and a press flips it and sends nothing; the next
   * slider move carries the new sign (ADR-0084).
   */
  private driving(cab: Cab) {
    const percent = Math.round(this.slider * 100);
    const way = this.reverse ? "Reverse" : "Forward";
    const moving = this.slider > 0;
    return html`
      <div class="reading">${percent}<span class="unit">%</span></div>
      <div class="motion">${this.reverse ? REVERSE : FORWARD}<span>${way}</span></div>
      <div
        class="track"
        role="slider"
        tabindex=${this.live ? 0 : -1}
        aria-label="speed"
        aria-orientation="vertical"
        aria-valuemin="0"
        aria-valuemax="1"
        aria-valuenow=${String(this.slider)}
        aria-valuetext=${`${percent} % ${way}`}
        aria-disabled=${String(!this.live)}
        style=${`--value: ${this.slider}`}
        @pointerdown=${(event: PointerEvent) => this.grab(cab.train, event)}
        @pointermove=${(event: PointerEvent) => this.dragging(cab.train, event)}
        @pointerup=${() => (this.drag = null)}
        @pointercancel=${() => (this.drag = null)}
        @keydown=${(event: KeyboardEvent) => this.keyed(cab.train, event)}
      >
        <span class="fill"></span>
        ${TICKS.map(
          (at) =>
            html`<b class=${at / 20 <= this.slider + 1e-9 ? "tick lit" : "tick"}
              style=${`--at: ${at}`}></b>`,
        )}
        <span class="thumb"><i></i><i></i><i></i></span>
      </div>
      <button
        class=${moving ? "go stop" : "go reverser"}
        aria-label=${moving
          ? "Stop"
          : `${way}: press for ${this.reverse ? "Forward" : "Reverse"}`}
        ?disabled=${!this.live}
        @click=${() => this.going(cab.train)}
      >
        ${moving ? SQUARE : this.reverse ? REVERSE : FORWARD}
      </button>
    `;
  }

  // --- what goes on the bus -------------------------------------------------

  /** A pointer down on the track. On the thumb, the drag starts from where
   *  the slider stands and nothing moves until the pointer does; anywhere
   *  else, the slider goes to the pointer first, 0 below its travel and 1
   *  above it, and the drag starts from there. */
  private grab(train: string, event: PointerEvent): void {
    const track = this.track;
    if (!this.live || track === null) return;
    track.setPointerCapture?.(event.pointerId);
    const box = track.getBoundingClientRect();
    const span = box.height - 2 * TRACK_PAD_PX;
    if (span > 0 && !(event.target as Element).closest(".thumb")) {
      this.slide(train, (box.bottom - TRACK_PAD_PX - event.clientY) / span);
    }
    this.drag = { pointer: event.pointerId, y: event.clientY, from: this.slider, span };
  }

  /** The pointer moved over the track: the slider by the distance it went
   *  up, over the track's usable height. */
  private dragging(train: string, event: PointerEvent): void {
    const drag = this.drag;
    if (drag === null || drag.pointer !== event.pointerId || drag.span <= 0) return;
    this.slide(train, drag.from + (drag.y - event.clientY) / drag.span);
  }

  /** A key on the track: the arrows a hundredth, PageUp and PageDown a
   *  tenth. */
  private keyed(train: string, event: KeyboardEvent): void {
    const by: Record<string, number> = {
      ArrowUp: STEP,
      ArrowRight: STEP,
      ArrowDown: -STEP,
      ArrowLeft: -STEP,
      PageUp: PAGE,
      PageDown: -PAGE,
    };
    const step = by[event.key];
    if (step === undefined) return;
    event.preventDefault();
    this.slide(train, this.slider + step);
  }

  /** Move the slider to `to`, held to 0–1 and to the hundredth, and drive
   *  the train there where that is a value it is not at already. */
  private slide(train: string, to: number): void {
    const value = Math.round(Math.min(1, Math.max(0, to)) * STEPS) / STEPS;
    if (value !== this.slider) this.drive(train, value);
  }

  /** The button under the slider: the stop above 0, the reverser at 0. */
  private going(train: string): void {
    if (!this.live) return;
    if (this.slider > 0) this.drive(train, 0);
    else this.reverse = !this.reverse;
  }

  /** The slider moved: one `throttle_wanted` carrying the number now shown,
   *  signed by the reverser. What is on screen and what went on the bus are
   *  the same value, which is the whole of the contract with a person's
   *  hand. */
  private drive(train: string, speed: number): void {
    if (!this.live) return;
    this.slider = speed;
    this.say<ThrottleWanted>("throttle-wanted", {
      train,
      speed: this.reverse && speed !== 0 ? -speed : speed,
      throttle: this.throttle,
    });
  }

  /** A function pressed: one `function_wanted` asking for the opposite of
   *  what the button shows. The button waits for `state/functions`. */
  private switching(train: string, name: string, on: boolean): void {
    if (!this.live || this.cab?.train !== train) return;
    this.say<FunctionWanted>("function-wanted", {
      train,
      throttle: this.throttle,
      function: name,
      on,
    });
  }

  /** A momentary function's button held: one `function_wanted` for on, and
   *  the hold remembered so that only its end asks for off. */
  private holding(train: string, name: string): void {
    if (!this.live || this.cab?.train !== train || this.held.has(name)) return;
    this.held.set(name, train);
    this.switching(train, name, true);
  }

  /** A momentary function's button let go of: one `function_wanted` for off,
   *  once for each hold however many of its ends arrive — a pointer up is
   *  followed by the capture's loss, a blur by the key coming up. Unguarded,
   *  where the start is guarded: over dead rails, or for a train this
   *  throttle no longer holds, the off still goes, and `layout` takes it at
   *  any power and drops it where the train is not this throttle's (#994). */
  private letting(train: string, name: string): void {
    if (this.held.get(name) !== train) return;
    this.held.delete(name);
    this.say<FunctionWanted>("function-wanted", {
      train,
      throttle: this.throttle,
      function: name,
      on: false,
    });
  }

  /** Every hold on the panel let go of, as `letting` lets go of one. */
  private lettingAll(): void {
    for (const [name, train] of [...this.held]) this.letting(train, name);
  }

  /** An event for the page. A panel being removed is out of the page
   *  already, so what it says then is said from the root it was drawn in. */
  private say<T>(name: string, detail: T): void {
    const from = this.isConnected ? this : this.home;
    from?.dispatchEvent(
      new CustomEvent<T>(name, { detail, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-driving": TcDriving;
  }
}
