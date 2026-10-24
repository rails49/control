/**
 * The railroad's fast clock on the band
 * ([ADR-0090](../../../docs/adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md),
 * decision 6): a small round face with hour and minute hands, `×8` beside
 * it where the speed-up is not 1, and the time, `HH:MM`, as its tooltip. It
 * draws what `tc49/layout/state/clock` last said and reads no wall clock;
 * with no railroad loaded or the broker not answering there is no clock and
 * nothing is drawn.
 *
 * Pressing it opens a dialog with the time and the speed-up. Saving fires
 * `clock-wanted` with only the fields the person changed, and the app
 * carries it to the session, which publishes `clock_wanted` — the view asks,
 * the app carries, the session writes, as the band's other presses go
 * (ADR-0074). What the face then shows is `state/clock` coming back.
 *
 * @fires clock-wanted - `CustomEvent<ClockChange>`: what was changed.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@rails49/look";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";

import {
  faster,
  hhmm,
  speedUpOf,
  timeOf,
  type ClockChange,
  type FastClock,
} from "../model/clock.js";
import { bandClockStyles } from "./tc-band-clock.styles.js";
import "./tc-clock.js";

@customElement("tc-band-clock")
export class TcBandClock extends LitElement {
  static override styles = bandClockStyles;

  /** The fast clock as the session last read it, `null` for none. */
  @property({ attribute: false }) clock: FastClock | null = null;

  /** What the dialog's fields say, as typed, `null` while it is shut. */
  @state() private typed: { time: string; speedUp: string } | null = null;

  /** What the fields said when the dialog opened: a field still saying it
   *  is a field the person did not change. */
  private opened = { time: "", speedUp: "" };

  override render() {
    const clock = this.clock;
    if (clock === null) return nothing;
    const time = hhmm(clock.time);
    const beside = faster(clock.speedUp);
    return html`
      <button class="face" title=${time} aria-label=${`fast clock ${time}`} @click=${this.open}>
        <tc-clock plain .time=${clock.time}></tc-clock>
        ${beside === "" ? nothing : html`<span class="faster">${beside}</span>`}
      </button>
      ${this.typed === null ? nothing : this.dialog(this.typed)}
    `;
  }

  private dialog(typed: { time: string; speedUp: string }) {
    const change = this.change(typed);
    return html`
      <look-dialog open size="small" label="Fast clock" @sl-after-hide=${this.close}>
        <div class="fields">
          <sl-input
            class="time"
            label="Time"
            type="time"
            size="small"
            value=${typed.time}
            @sl-input=${(event: Event) => this.type("time", event)}
          ></sl-input>
          <sl-input
            class="speed-up"
            label="Speed-up"
            type="number"
            size="small"
            min="0"
            step="any"
            value=${typed.speedUp}
            @sl-input=${(event: Event) => this.type("speedUp", event)}
          ></sl-input>
        </div>
        <sl-button slot="footer" class="cancel" @click=${this.close}>Cancel</sl-button>
        <sl-button
          slot="footer"
          variant="primary"
          class="save"
          ?disabled=${change === null}
          @click=${() => this.save(change)}
        >
          Save
        </sl-button>
      </look-dialog>
    `;
  }

  /** What the fields ask for, the fields left as they opened left out;
   *  `null` where one changed is not a time of day or a speed-up. */
  private change(typed: { time: string; speedUp: string }): ClockChange | null {
    const change: ClockChange = {};
    if (typed.time !== this.opened.time) {
      const time = timeOf(typed.time);
      if (time === null) return null;
      change.time = time;
    }
    if (typed.speedUp !== this.opened.speedUp) {
      const speedUp = speedUpOf(typed.speedUp);
      if (speedUp === null) return null;
      if (speedUp !== this.clock?.speedUp) change.speedUp = speedUp;
    }
    return change;
  }

  private open = (): void => {
    if (this.clock === null) return;
    this.opened = { time: hhmm(this.clock.time), speedUp: String(this.clock.speedUp) };
    this.typed = { ...this.opened };
  };

  private close = (): void => {
    this.typed = null;
  };

  private type(field: "time" | "speedUp", event: Event): void {
    if (this.typed === null) return;
    this.typed = { ...this.typed, [field]: (event.target as HTMLInputElement).value };
  }

  /** The change asked for, where there is one, and the dialog shut. */
  private save(change: ClockChange | null): void {
    this.typed = null;
    if (change === null || Object.keys(change).length === 0) return;
    this.dispatchEvent(
      new CustomEvent<ClockChange>("clock-wanted", {
        detail: change,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-band-clock": TcBandClock;
  }
}
