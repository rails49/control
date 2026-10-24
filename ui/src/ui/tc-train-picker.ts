/**
 * The throttle's train selector (ui/THROTTLE.md, ADR-0089,
 * [#967](https://github.com/rails49/control/issues/967)): what a panel of the
 * throttle view shows while its throttle holds no train, and what pressing
 * the picture of the train it holds opens over the whole panel. A card for
 * each placed train, two across, every one of them a press: the panel's own
 * train closes the selector, a free one is taken, and one another throttle
 * holds asks first, in a dialog inside the panel, since taking it releases it
 * there. Another throttle is any id but this panel's, the panel beside it on
 * the same page included. Below the cards, Release gives the panel's train
 * back.
 *
 * A train is not picked here without being taken: there is no selection to
 * hold, only the press. What the panel shows next is `state/taken` coming
 * back naming its throttle (ADR-0035), so a take `layout` drops changes
 * nothing on screen and the selector stays open.
 *
 * While the rails are dead or no broker answers, the cards, *Take train* and
 * Release are drawn dead (`aria-disabled`) and send nothing when pressed:
 * the press reaches the guard, so the guard is what keeps the train still.
 *
 * It works nothing out, as `tc-throttle` does not: the cabs say who holds
 * each train (`model/throttle.ts`), and the presses go to the app as
 * `take-wanted`, the train and this panel's throttle id its detail, and
 * `release-wanted`, the train its detail. Closing it is `selector-closed`,
 * to the panel and not the app: nothing goes on the bus.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { photoUrl } from "../model/store.js";
import { driveRefusal, type Cab } from "../model/throttle.js";
import type { Power } from "../model/trace.js";
import { pickerStyles } from "./tc-train-picker.styles.js";

/** A card pressed: the train, and the id of the panel's throttle that is to
 *  hold it — the one the app carries to `Session.pressTake`. */
export interface TakeWanted {
  train: string;
  throttle: string;
}

@customElement("tc-train-picker")
export class TcTrainPicker extends LitElement {
  static override styles = pickerStyles;

  /** The trains there are to drive, as the session orders them: by name. */
  @property({ attribute: false }) cabs: readonly Cab[] = [];

  /** The id of the panel's throttle (`Session.throttleFor`): what a take
   *  names, and what every other holder is told apart from. */
  @property() throttle = "";

  /** Whether a train may move at all, `null` before the layout has said. */
  @property() power: Power | null = null;

  /** Whether a session is joined and answering. */
  @property({ type: Boolean }) linked = false;

  /** The train another throttle holds whose take is being confirmed, `null`
   *  while no dialog is open. */
  @state() private asking: string | null = null;

  /** The models whose photo did not load, drawn by the train's name. */
  @state() private unseen: ReadonlySet<string> = new Set();

  /** The train `state/taken` names this panel's throttle for, the first by
   *  name where it names it for several, as `tc-throttle` draws it. */
  private get mine(): Cab | undefined {
    return this.cabs.find((cab) => cab.holder === this.throttle);
  }

  /** Why nothing can be sent, `null` where something can. */
  private get still(): string | null {
    return driveRefusal(this.linked, this.power);
  }

  override render() {
    const still = this.still;
    const mine = this.mine;
    const count = this.cabs.length;
    return html`
      <header>
        <div>
          <h2>Choose a train</h2>
          <p class="sub">${count} ${count === 1 ? "train" : "trains"} on the layout</p>
        </div>
        ${mine === undefined
          ? nothing
          : html`<button
              class="close"
              aria-label="Close"
              @click=${() => this.say<null>("selector-closed", null)}
            >
              ✕
            </button>`}
      </header>
      ${count === 0
        ? html`<p class="hint">
            ${this.linked ? "no train is on the layout — place one in the run view" : still}
          </p>`
        : html`
            ${still === null ? nothing : html`<p class="still">${still}</p>`}
            <ul class="cards">
              ${this.cabs.map((cab) => html`<li>${this.card(cab, still === null)}</li>`)}
            </ul>
          `}
      <footer>
        <button
          class="release"
          ?disabled=${mine === undefined}
          aria-disabled=${still !== null}
          @click=${() => this.releasing()}
        >
          ${mine === undefined ? "Release" : `Release ${mine.train}`}
        </button>
      </footer>
      ${this.asking === null ? nothing : this.dialog(this.asking)}
    `;
  }

  /** One train, the whole card the press: its picture, its name, where it
   *  stands, and who holds it where that is anybody. */
  private card(cab: Cab, live: boolean) {
    const kind =
      cab.holder === null ? "free" : cab.holder === this.throttle ? "mine" : "held";
    return html`
      <button
        class=${`card ${kind === "held" ? "faded" : kind}`}
        data-train=${cab.train}
        aria-disabled=${!live}
        @click=${() => this.choosing(cab)}
      >
        ${this.thumbnail(cab)}
        <span class="name">${cab.train}</span>
        <span class="where">${cab.block === null ? "crossing a transit" : `at ${cab.block}`}</span>
        ${kind === "mine"
          ? html`<span class="holder">driving here</span>`
          : kind === "held"
            ? html`<span class="holder">held by another throttle</span>`
            : nothing}
      </button>
    `;
  }

  /** Taking a train another throttle holds, asked inside the panel. */
  private dialog(train: string) {
    return html`<div class="confirm">
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="asking">
        <h3 id="asking">Take ${train}?</h3>
        <p>
          Another throttle is driving this train. Taking it releases it there first. In
          manual driving the train stops before it is yours.
        </p>
        <div class="row">
          <button class="cancel" @click=${() => (this.asking = null)}>Cancel</button>
          <button
            class="confirmed"
            aria-disabled=${this.still !== null}
            @click=${() => this.seizing(train)}>
            Take train
          </button>
        </div>
      </div>
    </div>`;
  }

  /** The model photo of the train's first locomotive, or its name where it
   *  has none or the photo does not load. */
  private thumbnail(cab: Cab) {
    const model = cab.locomotive;
    if (model === null || this.unseen.has(model)) {
      return html`<span class="thumbnail stand-in">${cab.train}</span>`;
    }
    return html`<img
      class="thumbnail"
      src=${photoUrl(model)}
      alt=${cab.train}
      @error=${() => (this.unseen = new Set([...this.unseen, model]))}
    />`;
  }

  // --- what goes on the bus -------------------------------------------------

  /**
   * A card pressed. The panel's own train: the selector closes. A free one:
   * the panel's train given back first where it holds one, then this one
   * taken — a throttle holds one train (ADR-0089). One another throttle
   * holds: the dialog, and nothing yet. Nothing at all while the rails are
   * dead or no broker answers.
   */
  private choosing(cab: Cab): void {
    if (this.still !== null) return;
    if (cab.holder === this.throttle) {
      this.say<null>("selector-closed", null);
    } else if (cab.holder !== null) {
      this.asking = cab.train;
    } else {
      const mine = this.mine;
      if (mine !== undefined) this.say<string>("release-wanted", mine.train);
      this.say<TakeWanted>("take-wanted", { train: cab.train, throttle: this.throttle });
    }
  }

  /** *Take train*: released where it is held, then taken here, in that
   *  order. `layout` drops the take if a third throttle took the train in
   *  between, and the selector then stays open. */
  private seizing(train: string): void {
    if (this.still !== null) return;
    this.asking = null;
    this.say<string>("release-wanted", train);
    this.say<TakeWanted>("take-wanted", { train, throttle: this.throttle });
  }

  /** Release: the panel's train given back, the same `null` take any release
   *  is (BUS.md, `take_wanted`). `layout` writes the speed a release implies,
   *  so this sends no zero of its own — one gesture per press. */
  private releasing(): void {
    const mine = this.mine;
    if (this.still !== null || mine === undefined) return;
    this.say<string>("release-wanted", mine.train);
  }

  private say<T>(name: string, detail: T): void {
    this.dispatchEvent(new CustomEvent<T>(name, { detail, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-train-picker": TcTrainPicker;
  }
}
