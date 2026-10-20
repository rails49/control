/**
 * The throttle's train picker (ui/THROTTLE.md,
 * [#853](https://github.com/rails49/control/issues/853)): what the throttle
 * view shows while this page's throttle holds no train. A card for each
 * placed train it does not hold, the photo of the train's first locomotive on
 * it, and on each the one press that train allows — Take on a free train,
 * Force release on one another throttle holds. The train this throttle last
 * held, standing free, comes first and apart, as Take back.
 *
 * A train is not picked here without being taken: there is no selection to
 * hold, only the press. What the view shows next is `state/taken` coming
 * back naming this throttle (ADR-0035), so a take `layout` drops changes
 * nothing on screen.
 *
 * It works nothing out, as `tc-throttle` does not: the cabs say who holds
 * each train and which was last held (`model/throttle.ts`), and the presses
 * go to the app as `take-wanted` and `release-wanted`, the train their
 * detail.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { photoUrl } from "../model/store.js";
import { driveRefusal, type Cab } from "../model/throttle.js";
import type { Power } from "../model/trace.js";
import { pickerStyles } from "./tc-train-picker.styles.js";

@customElement("tc-train-picker")
export class TcTrainPicker extends LitElement {
  static override styles = pickerStyles;

  /** The trains there are to drive, as the session orders them: the last
   *  train held first where it is free, then by name. Those this throttle
   *  holds get no card. */
  @property({ attribute: false }) cabs: readonly Cab[] = [];

  /** Whether a train may move at all, `null` before the layout has said. */
  @property() power: Power | null = null;

  /** Whether a session is joined and answering. */
  @property({ type: Boolean }) linked = false;

  /** The models whose photo did not load, drawn by the train's name. */
  @state() private unseen: ReadonlySet<string> = new Set();

  override render() {
    const still = driveRefusal(this.linked, this.power);
    const offered = this.cabs.filter((cab) => cab.taken !== "here");
    const back = offered.find((cab) => cab.last);
    const rest = offered.filter((cab) => !cab.last);
    return html`
      <h2>Take a train</h2>
      ${this.cabs.length === 0
        ? html`<p class="hint">
            ${this.linked ? "no train is on the layout — place one in the run view" : still}
          </p>`
        : html`
            ${still === null ? nothing : html`<p class="still">${still}</p>`}
            ${back === undefined ? nothing : this.card(back, still === null)}
            <ul class="cards">
              ${rest.map((cab) => html`<li>${this.card(cab, still === null)}</li>`)}
            </ul>
          `}
    `;
  }

  /** One train: its picture, its name, where it stands, and its press. */
  private card(cab: Cab, live: boolean) {
    const held = cab.taken === "elsewhere";
    const kind = cab.last ? "card back" : held ? "card faded" : "card";
    return html`
      <article class=${kind} data-train=${cab.train}>
        ${this.thumbnail(cab)}
        ${cab.last ? html`<span class="mine">You held this one</span>` : nothing}
        <span class="name">${cab.train}</span>
        <span class="where">${cab.block ?? "crossing a transit"}</span>
        ${held ? html`<span class="holder">held by another throttle</span>` : nothing}
        ${held
          ? html`<button
              class="force"
              ?disabled=${!live}
              @click=${() => this.say("release-wanted", cab.train, live)}
            >
              Force release
            </button>`
          : html`<button
              class=${cab.last ? "take back" : "take"}
              ?disabled=${!live}
              @click=${() => this.say("take-wanted", cab.train, live)}
            >
              ${cab.last ? "Take back" : "Take"}
            </button>`}
      </article>
    `;
  }

  /** The model photo of the train's first locomotive, or its name where it
   *  has none or the photo does not load. */
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

  /** A press, carried to the app: nothing at all while the rails are dead
   *  or no broker answers. */
  private say(name: string, train: string, live: boolean): void {
    if (!live) return;
    this.dispatchEvent(
      new CustomEvent<string>(name, { detail: train, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-train-picker": TcTrainPicker;
  }
}
