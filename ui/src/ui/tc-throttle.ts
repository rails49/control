/**
 * The throttle view (ui/THROTTLE.md): take a train, drive it, give it back
 * ([#207](https://github.com/rails49/control/issues/207)). It is a row of
 * throttles ([ADR-0089](../../../docs/adr/0089-a-throttle-holds-one-train.md)):
 * each a panel the size of a phone screen with its own throttle id, holding at
 * most one train. A panel whose throttle holds no train is the train selector
 * (`tc-train-picker`, [#853](https://github.com/rails49/control/issues/853));
 * one whose throttle holds a train is that train's driving controls
 * (`tc-driving`, laid out as `docs/ui/images/throttle-mockup.html`,
 * [#968](https://github.com/rails49/control/issues/968)), clock and all.
 * Pressing that train's picture opens the selector over the whole panel
 * ([#967](https://github.com/rails49/control/issues/967)), and it stays open
 * until it is closed or `state/taken` names the panel's throttle for the
 * train last chosen in it — never on the press itself.
 *
 * How many panels stand side by side, and how wide each is, is `panels` by
 * the view's own width and not the window's: one exactly the view's width on
 * a phone, as many as fit on a tablet. A panel holding a train that no
 * longer fits wraps onto a further row; an empty one is dropped. Narrowing the
 * view releases nothing.
 *
 * A view of this app beside the run view and the editor
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)),
 * and a person's actions on it ride the bus as gestures the inventory marks
 * browser-writable — `tc49/layout/take_wanted`,
 * `tc49/layout/throttle_wanted` and `tc49/layout/function_wanted`, each
 * naming the panel's throttle id, which the session mints per panel slot
 * (`throttleFor`) and keeps alive on `tc49/layout/throttle_alive`
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

import { panelHeight, panels, type Cab } from "../model/throttle.js";
import type { Power } from "../model/trace.js";
import "./tc-driving.js";
import "./tc-train-picker.js";
import type { TakeWanted } from "./tc-train-picker.js";
import { throttleStyles } from "./tc-throttle.styles.js";

@customElement("tc-throttle")
export class TcThrottle extends LitElement {
  static override styles = throttleStyles;

  /** The trains there are to drive, in the order they are offered: the ones
   *  the railroad has placed (`model/throttle.ts`). */
  @property({ attribute: false }) cabs: readonly Cab[] = [];

  /** The throttle id of panel slot `slot`, the same for the life of the
   *  page (`Session.throttleFor`): the app hands the session's in. */
  @property({ attribute: false }) throttleFor: (slot: number) => string = () => "";

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

  /** The view's own width and height in CSS pixels, as its `ResizeObserver`
   *  last said; 0 until it has, which lays it out as a phone. */
  @state() private width = 0;
  @state() private height = 0;

  /** The panel slots shown, in the order shown, kept for the life of the
   *  page: each slot is one throttle id. */
  private slots: number[] = [];

  /** How many panels `slots` was last fitted to, 0 before the first. */
  private fitted = 0;

  /** The slots whose selector is open over their train's controls. */
  @state() private open: ReadonlySet<number> = new Set();

  /** slot → the train last chosen in its selector, until `state/taken`
   *  names the slot's throttle for it. A take `layout` drops leaves it, and
   *  the selector open. */
  private chosen = new Map<number, string>();

  private watch = new ResizeObserver((entries) => {
    for (const entry of entries) {
      this.width = entry.contentRect.width;
      this.height = entry.contentRect.height || 0;
    }
  });

  override connectedCallback(): void {
    super.connectedCallback();
    this.watch.observe(this);
  }

  override disconnectedCallback(): void {
    this.watch.disconnect();
    super.disconnectedCallback();
  }

  /**
   * The slots fitted to the panels that now fit, where that count moved.
   * More: the lowest slots not shown go on the end. Fewer: panels holding no
   * train go, from the end, until the count is met — a panel holding a train
   * is never dropped and wraps onto a further row instead. Nothing is
   * published either way.
   */
  override willUpdate(): void {
    this.settle();
    const count = panels(this.width).count;
    if (count === this.fitted) return;
    this.fitted = count;
    const slots = [...this.slots];
    for (let slot = 0; slots.length < count; slot++) {
      if (!slots.includes(slot)) slots.push(slot);
    }
    for (let at = slots.length - 1; at >= 0 && slots.length > count; at--) {
      if (this.held(slots[at]!) === undefined) slots.splice(at, 1);
    }
    this.slots = slots;
  }

  /** Close each selector whose choice `state/taken` now names its panel's
   *  throttle for, and forget the open ones whose panel holds no train: the
   *  selector is shown in place there anyway. */
  private settle(): void {
    const open = new Set(this.open);
    for (const [slot, train] of this.chosen) {
      if (this.held(slot)?.train !== train) continue;
      this.chosen.delete(slot);
      open.delete(slot);
    }
    for (const slot of open) if (this.held(slot) === undefined) open.delete(slot);
    if (open.size !== this.open.size) this.open = open;
  }

  /** Open or close slot `slot`'s selector. */
  private opening(slot: number, open: boolean): void {
    const slots = new Set(this.open);
    if (open) slots.add(slot);
    else {
      slots.delete(slot);
      this.chosen.delete(slot);
    }
    this.open = slots;
  }

  override render() {
    const laid = panels(this.width);
    const height = panelHeight(this.height, laid.single);
    // Keyed by slot: a width change keeps each panel, and with it the
    // slider and reverser under a train that may be running (#876).
    return html`<main
      class=${laid.single ? "single" : "row"}
      style=${`--count: ${laid.count}`}
    >
      ${repeat(
        this.slots,
        (slot) => slot,
        (slot) => this.panel(slot, laid.width, height),
      )}
    </main>`;
  }

  /** One throttle: its train's driving controls, with the selector over
   *  them while it is open, or the selector alone while it holds none.
   *  `width` is 0 before the view has been measured, and the panel then
   *  takes the width it is given. A take chosen in the selector is noted on
   *  its way to the app, so the selector closes once it is answered. */
  private panel(slot: number, width: number, height: number) {
    const throttle = this.throttleFor(slot);
    const cab = this.held(slot);
    const size = `${width > 0 ? `width: ${width}px; ` : ""}height: ${height}px`;
    const selector = (over: boolean) => html`<tc-train-picker
      class=${over ? "over" : ""}
      .cabs=${this.cabs}
      .throttle=${throttle}
      .power=${this.power}
      .linked=${this.linked}
      @take-wanted=${(event: CustomEvent<TakeWanted>) =>
        this.chosen.set(slot, event.detail.train)}
      @selector-closed=${() => this.opening(slot, false)}
    ></tc-train-picker>`;
    return html`<section class="panel" data-slot=${slot} style=${size}>
      ${cab === undefined
        ? selector(false)
        : html`<tc-driving
              .cab=${cab}
              .throttle=${throttle}
              .power=${this.power}
              .linked=${this.linked}
              .current=${this.current}
              .railroad=${this.railroad}
              @selector-wanted=${() => this.opening(slot, true)}
            ></tc-driving>
            ${this.open.has(slot) ? selector(true) : nothing}`}
    </section>`;
  }

  /** The cab of the train `state/taken` names slot `slot`'s throttle for,
   *  the first by name where it names it for several. Read afresh: the bus
   *  moves under a person holding a slider. */
  private held(slot: number): Cab | undefined {
    const throttle = this.throttleFor(slot);
    return this.cabs.find((cab) => cab.holder === throttle);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-throttle": TcThrottle;
  }
}
