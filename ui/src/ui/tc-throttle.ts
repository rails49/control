/**
 * The throttle view (ui/THROTTLE.md): take a train, drive it, give it
 * back ([#207](https://github.com/rails49/control/issues/207)). While this
 * page's throttle holds no train it is the train picker (`tc-train-picker`,
 * [#853](https://github.com/rails49/control/issues/853)); while it holds one
 * it is that train's driving controls, laid out as
 * arrangement A ([#852](https://github.com/rails49/control/issues/852)): the
 * train's picture at the top with what it is reading over it, the reverser,
 * its functions, Turn around and the clock below on the left, and the speed,
 * the slider and STOP below on the right, where a right thumb is.
 *
 * A view of this app beside the run view and the editor
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)),
 * and a person's actions on it ride the bus as gestures the inventory marks
 * browser-writable — `tc49/layout/take_wanted` and
 * `tc49/layout/throttle_wanted`, each naming this page's throttle id, which
 * the session mints and keeps alive on `tc49/layout/throttle_alive`
 * ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
 * It reaches no command station, shows no
 * decoder step and names no hardware address: the UI reaches the bus and the
 * store and there is no other world for it.
 *
 * It works nothing out. Every train it offers, who holds each, which way
 * each points, what each is reading and what a person can switch on it arrive
 * as `Cab`s (`model/throttle.ts`), and the frames go to the app, which carries
 * them to the session, exactly as the band's power presses do.
 *
 * **The speed is in the train's frame.** The slider runs 0 to 1 and the
 * reverser gives it its sign: Forward nose first, `+`, Reverse tail first,
 * `−` (CONTEXT.md, **Reverser**). `layout` composes the sign each locomotive
 * is given from the train's facing and the way round its car is coupled — so
 * one slider drives a top-and-tail set and this view sends one number and
 * never a direction for a locomotive (CONTEXT.md, **Throttle**).
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { photoUrl } from "../model/store.js";
import { driveRefusal, type Cab } from "../model/throttle.js";
import type { Power } from "../model/trace.js";
import "./tc-clock.js";
import "./tc-train-picker.js";
import { throttleStyles } from "./tc-throttle.styles.js";

/** The slider moved: the train it is about, and the speed it now asks for,
 *  signed by the reverser. The view writes nothing itself — the session is
 *  the app's, and the app carries the press there as it carries the band's
 *  (ADR-0074's path, ui/THROTTLE.md). A take and a release carry the train
 *  alone, as `take-wanted` and `release-wanted`. */
export interface ThrottleWanted {
  train: string;
  speed: number;
}

/** How finely the slider divides its travel. Twenty steps is finer than a
 *  thumb on a phone resolves and coarser than the noise of a drag, and the
 *  number a person reads is what goes on the bus. */
const STEP = 0.05;

@customElement("tc-throttle")
export class TcThrottle extends LitElement {
  static override styles = throttleStyles;

  /** The trains there are to drive, in the order they are offered: the ones
   *  the railroad has placed (`model/throttle.ts`). */
  @property({ attribute: false }) cabs: readonly Cab[] = [];

  /** Whether a train may move at all, `null` while no session is joined or
   *  before the layout has said (ADR-0041). The view is dead while it is
   *  anything but `on`, and says which. */
  @property() power: Power | null = null;

  /** Whether a session is joined and answering. A gesture into a socket that
   *  is not there is swallowed, so the controls say so instead. */
  @property({ type: Boolean }) linked = false;

  /** Where the slider stands, as the person left it: 0 through 1. It is the
   *  view's own and not the bus's — nothing publishes a throttle's position
   *  back — so it is what this shows and, signed, what it last sent. */
  @state() private slider = 0;

  /** The reverser: Reverse where `true`, Forward where not. Like the slider
   *  it is the person's, and it sends nothing when it moves (ADR-0084). */
  @state() private reverse = false;

  /** The models whose photo did not load, drawn by the train's name. */
  @state() private unseen: ReadonlySet<string> = new Set();

  /** The train the controls were last drawn for, `null` while they were
   *  not: a train newly under them starts at rest, Forward. */
  private driven: string | null = null;

  override willUpdate(changed: Map<string, unknown>): void {
    // The track is off: nothing is moving, so neither is the slider.
    if (changed.has("power") && this.power === "off") this.slider = 0;
    if (!changed.has("cabs")) return;
    const cab = this.cab;
    const train = cab?.train ?? null;
    // A train newly held, or none: the slider starts at rest and the
    // reverser at Forward on every take, a position carried over from the
    // last hold being a speed this one was never driven at. Given back by
    // anybody — this view, a force release, or `layout` itself — or gone off
    // the layout, there is no slider to show at all.
    if (train !== this.driven) {
      this.driven = train;
      this.slider = 0;
      this.reverse = false;
      return;
    }
    const was = (changed.get("cabs") as readonly Cab[] | undefined)?.find(
      (one) => one.train === train,
    );
    // A granted move ended at its sensor: `layout` has written `0.0`, and
    // the slider shows the train standing. A frame that only leaves a train
    // with no move, where it had none, ends nothing.
    if (cab !== null && was?.granted === true && !cab.granted) this.slider = 0;
  }

  override render() {
    const cab = this.cab;
    if (cab === null) {
      return html`<tc-train-picker
        .cabs=${this.cabs}
        .power=${this.power}
        .linked=${this.linked}
      ></tc-train-picker>`;
    }
    return html`<main>${this.cabinet(cab)}</main>`;
  }

  /** The cab of the train this throttle holds, `null` where it holds none.
   *  Where `state/taken` names it for several, the first by name: side by
   *  side is [#855](https://github.com/rails49/control/issues/855)'s. Read
   *  afresh: the bus moves under a person holding a slider. */
  private get cab(): Cab | null {
    return (
      this.cabs
        .filter((cab) => cab.taken === "here")
        .sort((one, other) => one.train.localeCompare(other.train))[0] ?? null
    );
  }

  // --- driving one ----------------------------------------------------------

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
        ${this.picture(cab)}
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
          <tc-clock></tc-clock>
        </div>
        <div class="right">${this.driving(cab)}</div>
      </section>
    `;
  }

  /** The model photo of the train's first locomotive, or its name where it
   *  has none, the roster does not have it, or the photo does not load — a
   *  model with no photo filed answers 404, as the stock screen finds. */
  private picture(cab: Cab) {
    const model = cab.locomotive;
    if (model === null || this.unseen.has(model)) {
      return html`<div class="picture name">${cab.train}</div>`;
    }
    return html`<img
      class="picture"
      src=${photoUrl(model)}
      alt=${cab.train}
      @error=${() => (this.unseen = new Set([...this.unseen, model]))}
    />`;
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
   * them (ADR-0045). A train whose cars declare none shows none, which is
   * most of the stock a railroad owns.
   *
   * The buttons are **drawn and not live**: the gesture carrying a press is
   * declared and this view does not send it yet
   * ([#856](https://github.com/rails49/control/issues/856)). Drawing them is
   * what says a train has them; the day it sends it, this is where it is
   * sent from.
   */
  private functions(cab: Cab) {
    if (cab.functions.length === 0) return nothing;
    return html`
      <div class="functions">
        ${cab.functions.map(
          (one) => html`
            <button class="function" disabled title="no gesture carries a function yet">
              ${one.name}
            </button>
          `,
        )}
      </div>
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
    "tc-throttle": TcThrottle;
  }
}
