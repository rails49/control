/**
 * The roster pane: the trains the railroad owns, name, length and where each
 * of them is ([#169](https://github.com/rails49/control/issues/169),
 * [#170](https://github.com/rails49/control/issues/170)).
 *
 * It fills the shell's left-pane slot in the run view, where the editor puts
 * its palette
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 * One slot, a view's pane in it.
 *
 * A railroad's roster is every train it owns, whether on the layout or off it
 * ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md)), so a
 * train standing nowhere has a row like any other. That is what makes the pane
 * somewhere to drag a train **out of** and **back to**: a row dragged onto a
 * block places the train, and a train's marker dragged onto the pane takes it
 * off the layout.
 *
 * It works nothing out. The rows arrive as data, ordered, exactly as the run
 * view's overlay does — a pane that sorted or filtered would be a second party
 * deciding what the railroad has. Where a drag lands is the view's too: this
 * says a row was picked up and where the pointer let go, and nothing about
 * what is under it.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type { RosterRow } from "../model/panel.js";
import type { Run } from "../model/trace.js";
import { rosterStyles } from "./tc-roster.styles.js";

/** A row picked up, and where the pointer was when it was let go. Client
 *  pixels, because what they land on is the canvas's to say. */
export interface RosterDrag {
  train: string;
  x: number;
  y: number;
}

@customElement("tc-roster")
export class TcRoster extends LitElement {
  static override styles = rosterStyles;

  /** The trains, in the order they are drawn. The run view supplies them and
   *  the order is the model's (`panel.roster`). */
  @property({ attribute: false }) trains: readonly RosterRow[] = [];

  /** How the run stands, `null` while no session is joined. A placement is
   *  accepted only while the run is **held** (ADR-0037), so that is when a row
   *  may be dragged; the pane says so rather than letting a drag be swallowed
   *  by the dispatcher. */
  @property({ attribute: false }) run: Run | null = null;

  /** The row being dragged, so it reads as picked up. Nothing else about the
   *  drag is here: where it lands is the view's. */
  @state() private held: string | null = null;

  /** Whether a row may be picked up at all. A placement is accepted only
   *  while the run is held, so that is the whole of the rule. */
  private get pickable(): boolean {
    return this.run === "held";
  }

  override render() {
    return html`
      <h2>Trains</h2>
      ${this.trains.length === 0
        ? html`<p class="hint">no trains on the roster</p>`
        : html`
            <ul>
              ${this.trains.map((train) => this.row(train))}
            </ul>
          `}
      ${this.run === "running"
        ? html`<p class="hint">
            the run is running — hold it to place trains or take them off
          </p>`
        : nothing}
    `;
  }

  /** One train: its name, its length, and where the run has it. A train
   *  between two blocks stands in none and is on the layout all the same, so
   *  the cell says what it is doing rather than naming a block it has left,
   *  beside `off the layout` for a train that is not placed (CONTEXT.md,
   *  **Placed** and **Transit**). */
  private row({ train, block, length, placed }: RosterRow) {
    return html`
      <li
        class=${[
          placed ? "" : "off",
          this.held === train ? "held" : "",
          this.pickable ? "" : "still",
        ]
          .filter(Boolean)
          .join(" ")}
        @pointerdown=${(event: PointerEvent) => this.pick(event, train)}
        @pointerup=${(event: PointerEvent) => this.drop(event, train)}
        @pointercancel=${() => (this.held = null)}
      >
        <span class="name" title=${train}>${train}</span>
        <span class="length">${length === null ? nothing : length}</span>
        <span class="where">
          ${placed ? (block ?? "crossing a transit") : "off the layout"}
        </span>
      </li>
    `;
  }

  /** A press on a row takes hold of the train. The row captures the pointer,
   *  so the release lands here wherever it happens — the canvas is another
   *  element, and the drop has to be reported from one place. */
  private pick(event: PointerEvent, train: string): void {
    if (event.button !== 0 || !this.pickable) return;
    (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
    this.held = train;
  }

  /** The release: where the pointer let go, for the view to read against what
   *  it is painting. A release over the pane itself is a drag that went
   *  nowhere, and the view finds no block under it. */
  private drop(event: PointerEvent, train: string): void {
    if (this.held !== train) return;
    this.held = null;
    this.dispatchEvent(
      new CustomEvent<RosterDrag>("roster-dropped", {
        detail: { train, x: event.clientX, y: event.clientY },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-roster": TcRoster;
  }
}
