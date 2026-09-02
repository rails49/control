/**
 * The throttle view (ui/THROTTLE.md): pick a train, take it, drive it, give it
 * back ([#207](https://github.com/rails49/control/issues/207)).
 *
 * A view of this app beside the run view and the editor
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)),
 * and a person's actions on it ride the bus as the two gestures the inventory
 * marks browser-writable — `tc49/layout/mode_wanted` and
 * `tc49/layout/throttle_wanted`. It reaches no command station, shows no
 * decoder step and names no hardware address: the UI reaches the bus and the
 * store and there is no other world for it.
 *
 * It works nothing out. Every train it offers, who is driving each, which way
 * each points, what each is reading and what a person can switch on it arrive
 * as `Cab`s (`model/throttle.ts`), and the frames go out through the view that
 * holds the session, exactly as the band's power presses do.
 *
 * **The lever is in the train's frame.** `+` is the way the train points, and
 * `layout` composes the sign each locomotive is given from the train's facing
 * and the way round its car is coupled — so one lever drives a top-and-tail
 * set and this view sends one number and never a direction for a locomotive
 * (CONTEXT.md, **Throttle**). The facing is drawn beside the lever so a person
 * can see which physical direction `+` is before they move it.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type { Cab } from "../model/throttle.js";
import type { Mode, Power } from "../model/trace.js";
import { throttleStyles } from "./tc-throttle.styles.js";

/** A gesture the view asks for: the train it is about, and what is wanted of
 *  it. The view writes nothing itself — the session is the run view's, and
 *  the app carries the press there as it carries the band's (ADR-0051's
 *  path, ui/THROTTLE.md). */
export interface ModeWanted {
  train: string;
  mode: Mode;
}

export interface ThrottleWanted {
  train: string;
  speed: number;
}

/** How finely the lever divides its travel. Twenty steps each way is finer
 *  than a hand on a knob resolves and coarser than the noise of a drag, and
 *  the number a person reads is what goes on the bus. */
const STEP = 0.05;

/** What a person is told when a gesture would go nowhere, by what is in the
 *  way of it. Only one is ever shown, and each names the action that clears
 *  it: an emergency stop is cleared where a supply is switched back on
 *  (ADR-0041). */
const STILL: Record<Power, string | null> = {
  on: null,
  stopped: "emergency stop — clear it before driving",
  off: "the track has no power — switch it on to drive",
};

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

  /** The train this throttle is on, `null` while none is picked. */
  @state() private picked: string | null = null;

  /** Where the lever stands, as the person left it: −1 through 0 to +1. It
   *  is the view's own and not the bus's — nothing publishes a throttle's
   *  position back — so it is what this shows and what it last sent. */
  @state() private lever = 0;

  override willUpdate(changed: Map<string, unknown>): void {
    if (!changed.has("cabs")) return;
    // The train went off the layout, or the run let go of the picture. There
    // is nothing under the lever, so the throttle is on no train rather than
    // on the name of one that is gone.
    if (this.picked !== null && this.cab === null) this.letGo();
    // Given back by anything but this view — another tab, or `layout` itself
    // — the lever is not a person's any more and must not go on showing a
    // speed nobody is asking for.
    else if (this.cab !== null && this.cab.mode !== "manual" && this.lever !== 0) {
      this.lever = 0;
    }
  }

  override render() {
    return html`
      <nav class="trains">
        <h2>Trains</h2>
        ${this.cabs.length === 0
          ? html`<p class="hint">
              ${this.linked
                ? "no train is on the layout — place one in the run view"
                : "no session — the run view joins one"}
            </p>`
          : html`<ul>
              ${this.cabs.map((cab) => this.row(cab))}
            </ul>`}
      </nav>
      <main>${this.cab === null ? this.nothing() : this.cabinet(this.cab)}</main>
    `;
  }

  // --- picking a train ------------------------------------------------------

  /** The cab of the train that is picked, `null` where none is or where the
   *  picture no longer has it. Read afresh: the bus moves under a person
   *  holding a lever. */
  private get cab(): Cab | null {
    return this.cabs.find((cab) => cab.train === this.picked) ?? null;
  }

  /** One train to pick: its name, where it stands, and whether a person has
   *  it. *Manual* is `layout`'s word and is drawn wherever it is true —
   *  including a train another tab is driving, which is a thing worth seeing
   *  before you reach for it. */
  private row(cab: Cab) {
    const taken = cab.mode === "manual";
    return html`
      <li>
        <button
          class=${`train ${cab.train === this.picked ? "picked" : ""}`}
          data-train=${cab.train}
          aria-pressed=${cab.train === this.picked}
          @click=${() => this.pick(cab.train)}
        >
          <span class="name">${cab.train}</span>
          ${taken ? html`<span class="taken">manual</span>` : nothing}
          <span class="where">${cab.block ?? "crossing a transit"}</span>
        </button>
      </li>
    `;
  }

  /** A train picked up, or the same one again. The lever starts at rest on
   *  every train: a position carried over from the last one would be a speed
   *  this train was never driven at. */
  private pick(train: string): void {
    this.picked = train;
    this.lever = 0;
  }

  /** The throttle on no train, and the lever at rest with it. */
  private letGo(): void {
    this.picked = null;
    this.lever = 0;
  }

  private nothing() {
    return html`<p class="hint">pick a train to drive it</p>`;
  }

  // --- driving one ----------------------------------------------------------

  /** Whether a gesture can be sent at all: a session that is answering, over
   *  rails a train may move on. The view says which is missing, and every
   *  control that would write is dead while it is (ui/THROTTLE.md). */
  private get live(): boolean {
    return this.linked && this.power === "on";
  }

  /** Why nothing can be driven, or `null` where something can. */
  private get still(): string | null {
    if (!this.linked) return "no session — the run view joins one";
    return this.power === null ? "the layout has not said whether the track is live"
      : STILL[this.power];
  }

  private cabinet(cab: Cab) {
    const taken = cab.mode === "manual";
    const still = this.still;
    return html`
      <header>
        <h2>${cab.train}</h2>
        ${this.facing(cab)}
        <button
          class=${`take ${taken ? "release" : ""}`}
          ?disabled=${!this.live}
          @click=${() => this.wanting(cab.train, taken ? "automatic" : "manual")}
        >
          ${taken ? "Release" : "Take"}
        </button>
      </header>
      ${still === null ? nothing : html`<p class="still">${still}</p>`}
      ${taken ? this.driving(cab) : html`<p class="hint">take the train to drive it</p>`}
      ${this.road(cab)} ${this.functions(cab)}
    `;
  }

  /** Which way the train points, as an arrow and the end it runs to: what
   *  `+` on the lever means physically, before anything moves (CONTEXT.md,
   *  **Facing**). The scheduler's answer, drawn and not derived. */
  private facing(cab: Cab) {
    if (cab.nose === null) {
      return html`<span class="facing none">no facing</span>`;
    }
    return html`<span class="facing" title="the way the lever's + runs">
      <span class="arrow" aria-hidden="true">→</span> ${cab.nose}
    </span>`;
  }

  /**
   * The lever: −1 through 0 to +1, and a STOP that centres it in one press.
   *
   * The centre is a stop and is what a person reaches for when something is
   * wrong, so it is one gesture and not a slide back through every speed
   * between. Turning the train round is offered from here as well, and only
   * while the lever reads zero: flipping the facing under a moving train
   * would reverse it on the spot.
   */
  private driving(cab: Cab) {
    const inFlight = cab.inFlight;
    return html`
      <div class="lever">
        <input
          type="range"
          class="speed"
          min="-1"
          max="1"
          step=${STEP}
          .value=${String(this.lever)}
          ?disabled=${!this.live}
          aria-label="speed"
          @input=${(event: Event) =>
            this.drive(cab.train, Number((event.target as HTMLInputElement).value))}
        />
        <span class="reading">${this.lever.toFixed(2)}</span>
        <button class="stop" ?disabled=${!this.live} @click=${() => this.drive(cab.train, 0)}>
          STOP
        </button>
        <button
          class="turn"
          title=${inFlight
            ? "the train has a request in flight"
            : this.lever === 0
              ? "turn the train round where it stands"
              : "the lever must be at rest"}
          ?disabled=${!this.live || this.lever !== 0 || inFlight}
          @click=${() => this.turning(cab.train)}
        >
          Turn around
        </button>
      </div>
    `;
  }

  /** What the train is reading and what is in front of it: the aspect at the
   *  end it would leave by, and the blocks of the route it is committed to.
   *  A person driving by hand reads the signal, and this is where they read
   *  it (ADR-0025). */
  private road(cab: Cab) {
    return html`
      <div class="road">
        <span class="signal">
          ${cab.aspect === null
            ? html`<span class="hint">no signal ahead</span>`
            : html`<span class=${`aspect ${cab.aspect}`}>${cab.aspect}</span>`}
        </span>
        ${cab.ahead.length === 0
          ? html`<span class="hint">no route committed</span>`
          : html`<ol class="ahead">
              ${cab.ahead.map(
                (block) =>
                  html`<li class=${block.claim} title=${block.claim}>${block.block}</li>`,
              )}
            </ol>`}
      </div>
    `;
  }

  /**
   * What a person can switch on this train, by the names the catalogue gives
   * them (ADR-0045). A train whose cars declare none shows none, which is
   * most of the stock a railroad owns.
   *
   * The buttons are **drawn and not live**: a function reaches a decoder
   * through the device vocabulary, `layout` is its one writer, and no gesture
   * carries a function press yet — the two rows a throttle rides on are the
   * mode and the speed
   * ([#296](https://github.com/rails49/control/issues/296)). Drawing them is
   * what says a train has them; the day the gesture is declared, this is
   * where it is sent from.
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

  /** Take the train, or give it back. The view goes on reading who is driving
   *  off `state/mode` and marks nothing taken on its own press: `layout`
   *  holds the mode, and a person is holding a train when it says so
   *  (ADR-0035). */
  private wanting(train: string, mode: Mode): void {
    if (!this.live) return;
    // Given back, the lever is nobody's. `layout` writes the speed the
    // train's current grant implies on the way back to automatic, so this
    // sends no zero of its own — one gesture per press.
    if (mode === "automatic") this.lever = 0;
    this.say<ModeWanted>("mode-wanted", { train, mode });
  }

  /** The lever moved: one `throttle_wanted` carrying the number that is now
   *  shown. What is on screen and what went on the bus are the same value,
   *  which is the whole of the contract with a person's hand. */
  private drive(train: string, speed: number): void {
    if (!this.live) return;
    this.lever = speed;
    this.say<ThrottleWanted>("throttle-wanted", { train, speed });
  }

  /** Turn the train round where it stands: the same `reversal_wanted` the run
   *  view's menu writes, from the view where the lever it must be at rest for
   *  is. The scheduler flips the facing and the arrow above turns, which is
   *  the whole of the feedback — and the same lever then drives the train the
   *  other way physically. */
  private turning(train: string): void {
    if (!this.live || this.lever !== 0) return;
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
