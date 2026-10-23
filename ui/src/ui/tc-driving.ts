/**
 * One train's driving controls on the throttle view (ui/THROTTLE.md), laid
 * out as arrangement A ([#852](https://github.com/rails49/control/issues/852)):
 * the train's picture at the top with what it is reading over it, the
 * reverser, its functions, Turn around and — where the view asks for it — the
 * clock below on the left, and the speed, the slider and STOP below on the
 * right, where a right thumb is.
 *
 * `tc-throttle` draws one for each train this page's throttle holds
 * ([#855](https://github.com/rails49/control/issues/855)), and each owns its
 * own train's slider and reverser: they are the person's and not the bus's,
 * so they live with the pointer that moves them. Every press names this
 * column's train and no other, and goes to the app as an event, exactly as
 * the band's power presses do.
 *
 * **The speed is in the train's frame.** The slider runs 0 to 1 and the
 * reverser gives it its sign: Forward nose first, `+`, Reverse tail first,
 * `−` (GLOSSARY.md, **Reverser**). `layout` composes the sign each locomotive
 * is given from the train's facing and the way round its car is coupled — so
 * one slider drives a top-and-tail set and this sends one number and never a
 * direction for a locomotive (GLOSSARY.md, **Throttle**).
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { watchPicture, type Watching } from "../model/picture.js";
import { photoUrl, pictureUrl, RETRY_MS } from "../model/store.js";
import { driveRefusal, type Cab } from "../model/throttle.js";
import type { Power } from "../model/trace.js";
import "./tc-clock.js";
import { drivingStyles } from "./tc-driving.styles.js";

/** The slider moved: the train it is about, and the speed it now asks for,
 *  signed by the reverser. The view writes nothing itself — the session is
 *  the app's, and the app carries the press there as it carries the band's
 *  (ADR-0074's path, ui/THROTTLE.md). A take and a release carry the train
 *  alone, as `take-wanted` and `release-wanted`. */
export interface ThrottleWanted {
  train: string;
  speed: number;
}

/** A function button pressed: the train, the function by its catalogue
 *  name, and `on` the opposite of what the button shows — the one the app
 *  carries to `Session.pressFunction`. */
export interface FunctionWanted {
  train: string;
  function: string;
  on: boolean;
}

/** How many of a train's functions show before `>>`: the rest wait below it
 *  until a person opens them. */
const FIRST = 2;

/** How finely the slider divides its travel. Twenty steps is finer than a
 *  thumb on a phone resolves and coarser than the noise of a drag, and the
 *  number a person reads is what goes on the bus. */
const STEP = 0.05;

@customElement("tc-driving")
export class TcDriving extends LitElement {
  static override styles = drivingStyles;

  /** The train this column drives, as the session last answered for it:
   *  one `state/taken` names this throttle for. Read afresh on every frame —
   *  the bus moves under a person holding a slider. */
  @property({ attribute: false }) cab: Cab | null = null;

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

  /** The loaded railroad's name, which the camera app's route is under;
   *  `null` or `""` while none is loaded. */
  @property() railroad: string | null = null;

  /** Whether this column draws the page's one clock. The view has one, and
   *  says which of its parts carries it. */
  @property({ type: Boolean }) clock = false;

  /** Where the slider stands, as the person left it: 0 through 1. It is the
   *  column's own and not the bus's — nothing publishes a throttle's position
   *  back — so it is what this shows and, signed, what it last sent. */
  @state() private slider = 0;

  /** The reverser: Reverse where `true`, Forward where not. Like the slider
   *  it is the person's, and it sends nothing when it moves (ADR-0084). */
  @state() private reverse = false;

  /** Whether `>>` has the functions past the first two open. Closed on
   *  every take. */
  @state() private more = false;

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

  override willUpdate(changed: Map<string, unknown>): void {
    // The picture no longer wanted: no retry waits, and the next time it is
    // wanted it is asked for afresh.
    if (this.watched === null) this.unwatch();
    // The track is off: nothing is moving, so neither is the slider.
    if (changed.has("power") && this.power === "off") this.slider = 0;
    if (!changed.has("cab")) return;
    const cab = this.cab;
    const was = changed.get("cab") as Cab | null | undefined;
    // A column is drawn afresh for each take, so its train does not change
    // under it; were it to, the slider starts at rest and the reverser at
    // Forward, a position carried over being a speed this one was never
    // driven at.
    if (was?.train !== cab?.train) {
      this.unwatch();
      this.slider = 0;
      this.reverse = false;
      this.more = false;
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

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unwatch();
    this.follow(null);
  }

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
      <section class="top">
        ${this.thumbnail(cab)} ${this.picture()}
        <div class="over">
          <h2>${cab.train}</h2>
          ${this.signal(cab)}
          <span class="stands">${cab.block ?? "crossing a transit"}</span>
          ${this.road(cab)} ${this.holding(cab)}
        </div>
      </section>
      ${still === null ? nothing : html`<p class="still">${still}</p>`}
      <section class="below">
        <div class="left">
          ${this.reverser()} ${this.functions(cab)} ${this.turn(cab)}
          ${this.clock ? html`<tc-clock></tc-clock>` : nothing}
        </div>
        <div class="right">${this.driving(cab)}</div>
      </section>
    `;
  }

  /** The model photo of the train's first locomotive, or its name where it
   *  has none, the roster does not have it, or the photo does not load — a
   *  model with no photo filed answers 404, as the stock screen finds. */
  private thumbnail(cab: Cab) {
    const model = cab.locomotive;
    if (model === null || this.unseen.has(model)) {
      return html`<div class="thumbnail name">${cab.train}</div>`;
    }
    return html`<img
      class="thumbnail"
      src=${photoUrl(model)}
      alt=${cab.train}
      @error=${() => (this.unseen = new Set([...this.unseen, model]))}
    />`;
  }

  /**
   * The camera car's live picture, over the thumbnail, while all three hold:
   * this view is current, this throttle holds the train, and the train
   * carries a camera. Otherwise the page holds no connection to the camera
   * app (ui/THROTTLE.md). A stream that fails, ends or stalls takes it away
   * (`model/picture.ts`), and the thumbnail shows until it is asked for again
   * `RETRY_MS` later under a new `try`.
   */
  private picture() {
    if (this.frame === null) return nothing;
    return html`<img class="picture" src=${this.frame} alt="" />
      <span class="live">LIVE</span>`;
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
   *  still worth seeing. A column taken out of the page still updates, so
   *  it asks for nothing. */
  private get watched(): string | null {
    const cab = this.cab;
    if (!this.isConnected || !this.current || cab === null || !cab.camera || !this.railroad) {
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

  /** Release: the train given back, the same `null` take a Force release
   *  is (BUS.md, `take_wanted`). The view goes back to the picker once
   *  `state/taken` no longer names this throttle for it. */
  private holding(cab: Cab) {
    return html`<button
      class="release"
      ?disabled=${!this.live}
      @click=${() => this.releasing(cab.train)}
    >
      Release
    </button>`;
  }

  /**
   * Forward and Reverse, both shown, the current one pressed. Live only with
   * the slider at 0: a flip at speed reverses a rolling train, and a long
   * one can leave the rails (ADR-0084). Switching it sends nothing; the next
   * slider input carries the new sign.
   */
  private reverser() {
    const dead = !this.live || this.slider !== 0;
    const title = this.slider === 0 ? nothing : "the slider must be at 0";
    return html`
      <div class="reverser" role="group" aria-label="reverser">
        <button
          class="forward"
          aria-pressed=${!this.reverse}
          title=${title}
          ?disabled=${dead}
          @click=${() => this.reversing(false)}
        >
          Forward
        </button>
        <button
          class="reverse"
          aria-pressed=${this.reverse}
          title=${title}
          ?disabled=${dead}
          @click=${() => this.reversing(true)}
        >
          Reverse
        </button>
      </div>
    `;
  }

  /** Turn the train round where it stands, only while the slider reads zero:
   *  flipping the facing under a moving train would reverse it on the spot.
   *  Dead too while it has a request in flight (#295). */
  private turn(cab: Cab) {
    const inFlight = cab.inFlight;
    return html`<button
      class="turn"
      title=${inFlight
        ? "the train has a request in flight"
        : this.slider === 0
          ? "turn the train round where it stands"
          : "the slider must be at rest"}
      ?disabled=${!this.live || this.slider !== 0 || inFlight}
      @click=${() => this.turning(cab.train)}
    >
      Turn around
    </button>`;
  }

  /**
   * The speed, the slider and STOP.
   *
   * The speed reads as a whole percentage of the train's maximum, with no
   * sign — which end leads is said under it. The slider runs 0 at the bottom
   * to 1 at the top and is live whenever this throttle holds the train over
   * live rails, granted move or not (ADR-0081). STOP puts it to 0 in one
   * press: it is what a person reaches for when something is wrong.
   */
  private driving(cab: Cab) {
    const motion =
      this.slider === 0 ? "at rest" : this.reverse ? "tail first" : "nose first";
    return html`
      <span class="reading">${Math.round(this.slider * 100)} %</span>
      <span class="motion">${motion}</span>
      <input
        type="range"
        class="speed"
        min="0"
        max="1"
        step=${STEP}
        .value=${String(this.slider)}
        ?disabled=${!this.live}
        aria-label="speed"
        aria-orientation="vertical"
        @input=${(event: Event) =>
          this.drive(cab.train, Number((event.target as HTMLInputElement).value))}
      />
      <button class="stop" ?disabled=${!this.live} @click=${() => this.drive(cab.train, 0)}>
        STOP
      </button>
    `;
  }

  /** The aspect at the end the reverser points the train to: the end its
   *  facing names for Forward, the block's other end for Reverse. A person
   *  driving by hand reads the signal, and this is where they read it
   *  (ADR-0025). */
  private signal(cab: Cab) {
    const aspect = this.reverse ? cab.tailAspect : cab.aspect;
    return html`<span class="signal">
      ${aspect === null
        ? html`<span class="hint">no signal ahead</span>`
        : html`<span class=${`aspect ${aspect}`}>${aspect}</span>`}
    </span>`;
  }

  /** The blocks of the route the train is committed to, in the two colours
   *  a route is lit in on the run view. */
  private road(cab: Cab) {
    return cab.ahead.length === 0
      ? html`<span class="hint">no route committed</span>`
      : html`<ol class="ahead">
          ${cab.ahead.map(
            (block) => html`<li class=${block.claim} title=${block.claim}>${block.block}</li>`,
          )}
        </ol>`;
  }

  /**
   * What a person can switch on this train, by the names the catalogue gives
   * them (ADR-0045), in the order the roster lists them. A train whose cars
   * declare none shows none, which is most of the stock a railroad owns.
   *
   * The first two always show; with three or more, `>>` follows them and
   * opens the rest below, in the same order. Each latches: a press asks for
   * the opposite of what the button shows, and the button shows what
   * `state/functions` says, `aria-pressed` where it is on — it changes when
   * `layout` says it switched it and not when it was pressed
   * ([#856](https://github.com/rails49/control/issues/856)). Live whenever
   * this throttle holds the train over live rails, granted move or not, and
   * otherwise drawn with their state and dead.
   */
  private functions(cab: Cab) {
    if (cab.functions.length === 0) return nothing;
    const button = (one: Cab["functions"][number]) => html`
      <button
        class="function"
        aria-pressed=${one.on}
        ?disabled=${!this.live}
        @click=${() => this.switching(cab.train, one.name, !one.on)}
      >
        ${one.name}
      </button>
    `;
    const rest = cab.functions.slice(FIRST);
    return html`
      <div class="functions">
        ${cab.functions.slice(0, FIRST).map(button)}
        ${rest.length === 0
          ? nothing
          : html`<button
              class="more"
              aria-expanded=${this.more}
              aria-label="more functions"
              @click=${() => (this.more = !this.more)}
            >
              &gt;&gt;
            </button>`}
      </div>
      ${this.more && rest.length > 0
        ? html`<div class="functions rest">${rest.map(button)}</div>`
        : nothing}
    `;
  }

  // --- what goes on the bus -------------------------------------------------

  /** Give the train back. `layout` writes the speed a release implies, so
   *  this sends no zero of its own — one gesture per press. */
  private releasing(train: string): void {
    if (!this.live) return;
    this.slider = 0;
    this.say<string>("release-wanted", train);
  }

  /** The reverser switched: nothing on the bus (ADR-0084). */
  private reversing(reverse: boolean): void {
    if (!this.live || this.slider !== 0) return;
    this.reverse = reverse;
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
    });
  }

  /** A function pressed: one `function_wanted` asking for the opposite of
   *  what the button shows. The button waits for `state/functions`. */
  private switching(train: string, name: string, on: boolean): void {
    if (!this.live || this.cab?.train !== train) return;
    this.say<FunctionWanted>("function-wanted", { train, function: name, on });
  }

  /** Turn the train round where it stands: the same `reversal_wanted` the run
   *  view's menu writes. The scheduler flips the facing, and the same
   *  reverser then drives the train the other way physically. */
  private turning(train: string): void {
    if (!this.live || this.slider !== 0) return;
    this.say<string>("reversal-wanted", train);
  }

  private say<T>(name: string, detail: T): void {
    this.dispatchEvent(
      new CustomEvent<T>(name, { detail, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-driving": TcDriving;
  }
}
