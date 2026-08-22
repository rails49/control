/**
 * The roster pane: the trains the run has, name, length and where each of them
 * stands ([#169](https://github.com/rails49/control/issues/169)).
 *
 * It fills the shell's left-pane slot in the run view, where the editor puts
 * its palette
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * One slot, a view's pane in it.
 *
 * **Read-only, and a list of what is *placed*.** A railroad's roster is every
 * train it owns, whether on the layout or off it
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)), and
 * there is nothing to read one from yet: the store serves no roster and
 * `state/allocation` carries the placed trains alone. So this lists what the
 * run holds, and gains the rest of the roster and its drags with
 * [#170](https://github.com/rails49/control/issues/170).
 *
 * It works nothing out. The rows arrive as data, ordered, exactly as the run
 * view's overlay does — a pane that sorted or filtered would be a second party
 * deciding what the run has.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { Placed } from "../model/panel.js";
import { rosterStyles } from "./tc-roster.styles.js";

/** One train on the pane: where the run says it is, and how long it is. */
export interface RosterRow extends Placed {
  /** Its length, `null` where nothing the page has read names one. Until the
   *  store serves a roster (#170) the only source is the scenario the session
   *  runs, so a train the run has and that document does not name has none. */
  length: number | null;
}

@customElement("tc-roster")
export class TcRoster extends LitElement {
  static override styles = rosterStyles;

  /** The trains, in the order they are drawn. The run view supplies them and
   *  the order is the model's (`Panel.placed`). */
  @property({ attribute: false }) trains: readonly RosterRow[] = [];

  override render() {
    return html`
      <h2>Trains</h2>
      ${this.trains.length === 0
        ? html`<p class="hint">no trains on the layout</p>`
        : html`
            <ul>
              ${this.trains.map((train) => this.row(train))}
            </ul>
          `}
    `;
  }

  /** One train. A train between two blocks stands in none and is on the
   *  layout all the same — it is holding a transit — so it says that rather
   *  than naming a block it has left (CONTEXT.md, **Placed**). */
  private row({ train, block, length }: RosterRow) {
    return html`
      <li>
        <span class="name" title=${train}>${train}</span>
        <span class="length">${length === null ? nothing : length}</span>
        <span class="where">${block ?? "crossing"}</span>
      </li>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-roster": TcRoster;
  }
}
