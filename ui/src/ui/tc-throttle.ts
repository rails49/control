/**
 * The throttle view (ui/THROTTLE.md): take a train, drive it, give it
 * back ([#207](https://github.com/rails49/control/issues/207)). While this
 * page's throttle holds no train it is the train picker (`tc-train-picker`,
 * [#853](https://github.com/rails49/control/issues/853)); while it holds
 * some it is their driving controls (`tc-driving`, arrangement A,
 * [#852](https://github.com/rails49/control/issues/852)), one column for each
 * train ([#855](https://github.com/rails49/control/issues/855)).
 *
 * Where the view is wide enough (`columns`, by its own width and not the
 * window's), the columns stand side by side and a take column on the right
 * carries the page's one clock and the trains to take; held trains beyond
 * the columns that fit go on a further row. On a phone there is no take
 * column, and the trains' controls stand one below the other, the first
 * carrying the clock. Narrowing the view releases nothing and hides nothing.
 * Every train is held under the page's one throttle id.
 *
 * A view of this app beside the run view and the editor
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)),
 * and a person's actions on it ride the bus as gestures the inventory marks
 * browser-writable — `tc49/layout/take_wanted`,
 * `tc49/layout/throttle_wanted` and `tc49/layout/function_wanted`, each naming this page's throttle id, which
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
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";

import { columns, type Cab } from "../model/throttle.js";
import type { Power } from "../model/trace.js";
import "./tc-clock.js";
import "./tc-driving.js";
import "./tc-train-picker.js";
import { throttleStyles } from "./tc-throttle.styles.js";

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

  /** Whether this is the view on screen, set by the app as `tc-panel`'s is.
   *  The camera car's picture is drawn only while it is: a view switched away
   *  holds no connection to the camera app. */
  @property({ type: Boolean }) current = false;

  /** The loaded railroad's name, which the camera app's route is under;
   *  `null` or `""` while none is loaded. */
  @property() railroad: string | null = null;

  /** The view's own width in CSS pixels, as its `ResizeObserver` last
   *  said; 0 until it has, which lays it out as a phone. */
  @state() private width = 0;

  /** The trains this throttle holds, in the order `state/taken` first named
   *  it for each: the order of the columns, kept for the life of the page. A
   *  train newly held goes after the others, and one given back leaves the
   *  others where they were. */
  private order: readonly string[] = [];

  private watch = new ResizeObserver((entries) => {
    for (const entry of entries) this.width = entry.contentRect.width;
  });

  override connectedCallback(): void {
    super.connectedCallback();
    this.watch.observe(this);
  }

  override disconnectedCallback(): void {
    this.watch.disconnect();
    super.disconnectedCallback();
  }

  override willUpdate(changed: Map<string, unknown>): void {
    if (!changed.has("cabs")) return;
    const here = this.cabs.filter((cab) => cab.taken === "here").map((cab) => cab.train);
    this.order = [
      ...this.order.filter((train) => here.includes(train)),
      ...here.filter((train) => !this.order.includes(train)),
    ];
  }

  override render() {
    const held = this.held;
    if (held.length === 0) {
      return html`<tc-train-picker
        .cabs=${this.cabs}
        .power=${this.power}
        .linked=${this.linked}
      ></tc-train-picker>`;
    }
    // One structure at every width, its layout by class alone: crossing
    // the stacked/side line keeps each train's `tc-driving`, and with it the
    // slider and reverser under a train that may be running (#876).
    const fit = columns(this.width);
    const stacked = fit === 0;
    return html`<main class=${stacked ? "stacked" : "side"}>
      <div class="trains" style=${`--columns: ${Math.max(fit, 1)}`}>
        ${repeat(
          held,
          (cab) => cab.train,
          (cab, index) => this.column(cab, stacked && index === 0),
        )}
      </div>
      ${stacked
        ? nothing
        : html`<aside class="take">
            <tc-clock></tc-clock>
            <h2>Take another train</h2>
            ${held.length >= fit
              ? html`<p class="hint">no room for another train — release one</p>`
              : html`<tc-train-picker
                  compact
                  .cabs=${this.cabs}
                  .power=${this.power}
                  .linked=${this.linked}
                ></tc-train-picker>`}
          </aside>`}
    </main>`;
  }

  /** One train's driving controls, the clock among them only where the view
   *  has no take column to carry it. */
  private column(cab: Cab, clock: boolean) {
    return html`<tc-driving
      .cab=${cab}
      .power=${this.power}
      .linked=${this.linked}
      .current=${this.current}
      .railroad=${this.railroad}
      ?clock=${clock}
    ></tc-driving>`;
  }

  /** The cabs of the trains this throttle holds, in the columns' order. Read
   *  afresh: the bus moves under a person holding a slider. */
  private get held(): Cab[] {
    return this.order
      .map((train) => this.cabs.find((cab) => cab.train === train))
      .filter((cab): cab is Cab => cab !== undefined);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-throttle": TcThrottle;
  }
}
