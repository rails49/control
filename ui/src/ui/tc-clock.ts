/**
 * The station clock on the throttle's cab (ui/THROTTLE.md,
 * [#852](https://github.com/rails49/control/issues/852)): the browser's local
 * wall time, drawn as the clock on a platform. It stays wall time until the
 * railroad has a fast clock.
 *
 * A face of 100 units, twelve bar markers, an hour and a minute hand, and a
 * red second hand with no disc at its tip. Each hand is drawn pointing at
 * twelve and turned to its angle, so the angles are the whole of the drawing:
 * the hour hand at `h×30 + m×0.5` degrees, the minute hand at `m×6 + s×0.1`,
 * the second hand at `s×6`. Redrawn once a second.
 */

import { LitElement, html, svg } from "lit";
import { customElement, state } from "lit/decorators.js";

import { clockStyles } from "./tc-clock.styles.js";

/** The middle of the face, in its own units. */
const C = 50;

@customElement("tc-clock")
export class TcClock extends LitElement {
  static override styles = clockStyles;

  /** The time drawn, read afresh each second. */
  @state() private now = new Date();

  private ticking: ReturnType<typeof setInterval> | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    this.now = new Date();
    this.ticking = setInterval(() => (this.now = new Date()), 1000);
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this.ticking !== null) clearInterval(this.ticking);
    this.ticking = null;
  }

  override render() {
    const h = this.now.getHours() % 12;
    const m = this.now.getMinutes();
    const s = this.now.getSeconds();
    return html`
      <svg viewBox="0 0 100 100" role="img" aria-label=${this.now.toLocaleTimeString()}>
        <circle class="face" cx=${C} cy=${C} r="48" />
        ${Array.from(
          { length: 12 },
          (_, at) =>
            svg`<line class="marker" x1=${C} y1="6" x2=${C} y2="16"
              transform=${`rotate(${at * 30} ${C} ${C})`} />`,
        )}
        ${hand("hour", h * 30 + m / 2, 62, 28)}
        ${hand("minute", m * 6 + s / 10, 62, 10)}
        ${hand("second", s * 6, 66, 10)}
      </svg>
    `;
  }
}

/** One hand at `degrees` clockwise from twelve, reaching `tail` units past
 *  the middle behind and to `tip` units from the top of the face. */
function hand(name: string, degrees: number, tail: number, tip: number) {
  return svg`<line class=${name} x1=${C} y1=${tail} x2=${C} y2=${tip}
    transform=${`rotate(${degrees} ${C} ${C})`} />`;
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-clock": TcClock;
  }
}
