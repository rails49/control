/**
 * The throttle view (ui/THROTTLE.md): take a train, drive it, give it
 * back ([#207](https://github.com/rails49/control/issues/207)). While this
 * page's throttle holds no train it is the train picker (`tc-train-picker`,
 * [#853](https://github.com/rails49/control/issues/853)); while it holds one
 * it is that train's driving controls (`tc-driving`, arrangement A,
 * [#852](https://github.com/rails49/control/issues/852)).
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

import { LitElement, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { Cab } from "../model/throttle.js";
import type { Power } from "../model/trace.js";
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

  override render() {
    const cab = this.cab;
    if (cab === null) {
      return html`<tc-train-picker
        .cabs=${this.cabs}
        .power=${this.power}
        .linked=${this.linked}
      ></tc-train-picker>`;
    }
    return html`<main>
      <tc-driving
        .cab=${cab}
        .power=${this.power}
        .linked=${this.linked}
        .current=${this.current}
        .railroad=${this.railroad}
        clock
      ></tc-driving>
    </main>`;
  }

  /** The cab of the train this throttle holds, `null` where it holds none.
   *  Where `state/taken` names it for several, the first by name: side by
   *  side is [#855](https://github.com/rails49/control/issues/855)'s. */
  private get cab(): Cab | null {
    return (
      this.cabs
        .filter((cab) => cab.taken === "here")
        .sort((one, other) => one.train.localeCompare(other.train))[0] ?? null
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-throttle": TcThrottle;
  }
}
