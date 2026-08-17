/**
 * The derived netlist, beside the canvas, redrawn as you edit.
 *
 * This is the feature the rest of the editor exists to serve. Drawing a
 * railroad is the easy half; the hard half is knowing that the picture means
 * what you think it means, because what the dispatcher runs is the netlist,
 * and the interesting part of that netlist is which movements may run at the
 * same time. Airolo's WX310 composes 19 transits and 33 concurrent pairs out
 * of four turnouts and a crossing, and nobody can confirm 33 pairs by reading
 * them.
 *
 * So selecting a transit lights its way on the canvas and lists every other
 * transit at that connection as concurrent or excluded, naming the symbol they
 * share. *Exclusive because both take `sw16`* is a claim about the drawing
 * that can be checked by looking at it.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { Review } from "../model/store.js";
import { netlistStyles } from "./styles.js";

/** Which transit is selected, as the connection and the name within it. */
export interface Chosen {
  connection: string;
  transit: string;
}

@customElement("tc-netlist")
export class TcNetlist extends LitElement {
  static override styles = netlistStyles;

  @property({ attribute: false }) review: Review | null = null;
  @property({ attribute: false }) chosen: Chosen | null = null;

  override render() {
    const layout = this.review?.layout;
    if (layout === null || layout === undefined) {
      return html`<p class="hint">No netlist: the drawing does not derive.</p>`;
    }
    return html`
      <h2>Blocks</h2>
      <ul class="blocks">
        ${Object.entries(layout.blocks).map(
          ([block, { length }]) =>
            html`<li><span>${block}</span><span>${length}</span></li>`,
        )}
      </ul>
      ${Object.keys(layout.connections).map((name) => this.connection(name))}
    `;
  }

  private connection(name: string) {
    const connection = this.review!.layout!.connections[name]!;
    return html`
      <h2>${name}</h2>
      <ul class="transits">
        ${Object.entries(connection.transits).map(
          ([transit, ends]) => html`
            <li>
              <button
                class=${this.isChosen(name, transit) ? "on" : ""}
                @click=${() => this.choose(name, transit)}
              >
                <span class="transit">${transit}</span>
                <span class="ends">${ends.join("  ")}</span>
              </button>
              ${this.isChosen(name, transit) ? this.against(name, transit) : nothing}
            </li>
          `,
        )}
      </ul>
    `;
  }

  /** Every other transit at this connection, split into those that can run
   *  with it and those that cannot, each with the reason. */
  private against(connection: string, transit: string) {
    const derived = this.review!.layout!.connections[connection]!;
    const explained = this.review?.explain?.connections[connection];
    const concurrent = new Set(
      (derived.concurrent ?? [])
        .filter((pair) => pair.includes(transit))
        .map((pair) => (pair[0] === transit ? pair[1] : pair[0])),
    );
    const others = Object.keys(derived.transits).filter(
      (other) => other !== transit,
    );
    return html`
      <ul class="against">
        ${others.map((other) => {
          const shared = (explained?.exclusive ?? []).find(
            (pair) =>
              pair.transits.includes(transit) && pair.transits.includes(other),
          );
          return html`
            <li class=${concurrent.has(other) ? "with" : "without"}>
              <span>${other}</span>
              <span class="why">
                ${concurrent.has(other)
                  ? "runs together"
                  : `shares ${shared?.shared.join(", ") ?? "the way"}`}
              </span>
            </li>
          `;
        })}
      </ul>
    `;
  }

  private isChosen(connection: string, transit: string): boolean {
    return (
      this.chosen?.connection === connection && this.chosen?.transit === transit
    );
  }

  private choose(connection: string, transit: string): void {
    const chosen = this.isChosen(connection, transit)
      ? null
      : { connection, transit };
    this.dispatchEvent(
      new CustomEvent<Chosen | null>("transit-chosen", {
        detail: chosen,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-netlist": TcNetlist;
  }
}
