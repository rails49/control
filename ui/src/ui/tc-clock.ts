/**
 * The station clock (ui/THROTTLE.md,
 * [#852](https://github.com/rails49/control/issues/852)): the railroad's fast
 * clock, drawn as the clock on a platform. It draws the time it is handed,
 * which is what `tc49/layout/state/clock` last said
 * ([ADR-0090](../../../docs/adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)),
 * and reads no clock of its own — so it moves when the row does, once a real
 * second, and its second hand steps by the speed-up.
 *
 * A face of 100 units, twelve bar markers, an hour and a minute hand, and a
 * red second hand with no disc at its tip. Each hand is drawn pointing at
 * twelve and turned to its angle, so the angles are the whole of the drawing:
 * the hour hand at `h×30 + m×0.5` degrees, the minute hand at `m×6 + s×0.1`,
 * the second hand at `s×6`. With no time — no railroad loaded, or the broker
 * not answering — the face is drawn with no hands. The band's face has no
 * second hand (`plain`).
 */

import { LitElement, html, nothing, svg } from "lit";
import { customElement, property } from "lit/decorators.js";

import { hhmm } from "../model/clock.js";
import { clockStyles } from "./tc-clock.styles.js";

/** The middle of the face, in its own units. */
const C = 50;

@customElement("tc-clock")
export class TcClock extends LitElement {
  static override styles = clockStyles;

  /** The time drawn, fast seconds since midnight, `null` for none. */
  @property({ type: Number }) time: number | null = null;

  /** Hour and minute hands only, as the band draws it. */
  @property({ type: Boolean }) plain = false;

  override render() {
    const time = this.time;
    const s = time === null ? 0 : time % 60;
    const m = time === null ? 0 : Math.floor(time / 60) % 60;
    const h = time === null ? 0 : Math.floor(time / 3600) % 12;
    return html`
      <svg viewBox="0 0 100 100" role="img" aria-label=${time === null ? "no clock" : hhmm(time)}>
        <circle class="face" cx=${C} cy=${C} r="48" />
        ${Array.from(
          { length: 12 },
          (_, at) =>
            svg`<line class="marker" x1=${C} y1="6" x2=${C} y2="16"
              transform=${`rotate(${at * 30} ${C} ${C})`} />`,
        )}
        ${time === null
          ? nothing
          : svg`${hand("hour", h * 30 + m / 2, 62, 28)}
            ${hand("minute", m * 6 + s / 10, 62, 10)}
            ${this.plain ? nothing : hand("second", s * 6, 66, 10)}`}
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
