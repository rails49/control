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
 * that can be checked by looking at it. Selecting a symbol gives the inverse:
 * every transit through it, split into those that can run together and those
 * that cannot.
 *
 * What each of those means is `inspect.ts`; this component only draws it.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import {
  WHOLE,
  against,
  amongst,
  routes,
  through,
  type Chosen,
  type Pair,
} from "../model/inspect.js";
import type { Review } from "../model/store.js";
import { netlistStyles } from "./tc-netlist.styles.js";

export type { Chosen } from "../model/inspect.js";

@customElement("tc-netlist")
export class TcNetlist extends LitElement {
  static override styles = netlistStyles;

  @property({ attribute: false }) review: Review | null = null;
  @property({ attribute: false }) chosen: Chosen | null = null;
  /** The one symbol selected on the canvas, where exactly one is. */
  @property({ attribute: false }) symbol: string | null = null;

  override render() {
    const layout = this.review?.layout;
    if (layout === null || layout === undefined) {
      return html`<p class="hint">No netlist: the drawing does not derive.</p>`;
    }
    const connections = Object.keys(layout.connections);
    return html`
      ${this.inspected()}
      <h2>
        ${layout.layout}
        <span class="count">
          ${count(Object.keys(layout.blocks).length, "block")},
          ${count(connections.length, "connection")}
        </span>
      </h2>
      <ul class="blocks">
        ${Object.entries(layout.blocks).map(
          ([block, { length }]) =>
            html`<li><span>${block}</span><span>${length}</span></li>`,
        )}
      </ul>
      ${connections.map((name) => this.connection(name))}
    `;
  }

  /** One connection as `tc49 layout show` prints it: its transits with their
   *  two block ends, and the pairs of them that run at the same time.
   *
   *  Headed by the symbols it is drawn from, which is the one place a name
   *  nobody typed can be read back. A junction of several throats wired
   *  together with no block between them is one connection, and reading its
   *  members is how that is seen rather than guessed at from a canvas tint. */
  private connection(name: string) {
    const connection = this.review!.layout!.connections[name]!;
    const concurrent = connection.concurrent ?? [];
    return html`
      <h3>${name}</h3>
      ${this.drawnFrom(name)}
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
              ${this.isChosen(name, transit)
                ? this.against(name, transit)
                : nothing}
            </li>
          `,
        )}
      </ul>
      <ul class="concurrent">
        ${concurrent.map(
          ([one, two]) => html`<li>${one} + ${two}</li>`,
        )}
      </ul>
    `;
  }

  /** The symbols a connection is drawn from: a junction's members, or nothing
   *  for a joint, which is a bare wire between two blocks and has none. */
  private drawnFrom(name: string) {
    const junction = (this.review?.junctions ?? []).find(
      (one) => one.name === name,
    );
    if (junction === undefined) return nothing;
    return html`<p class="drawn-from">${junction.symbols.join(" ")}</p>`;
  }

  /** Every other transit at this connection, split into those that can run
   *  with it and those that cannot, each with the reason. */
  private against(connection: string, transit: string) {
    return html`
      <ul class="against">
        ${against(this.review!, connection, transit).map(
          (other) => html`
            <li class=${other.concurrent ? "with" : "without"}>
              <span>${other.transit}</span>
              <span class="why">
                ${other.concurrent
                  ? "runs together"
                  : `shares ${other.shared.join(", ") || "the way"}`}
              </span>
            </li>
          `,
        )}
      </ul>
    `;
  }

  /**
   * The inverse of choosing a transit: one symbol, every transit through it,
   * and the pairs among them that do and do not run together.
   *
   * The leg each takes is what makes the split readable — two ways over one
   * frog can never run, and two on different legs run exactly when the symbol
   * says so — while `shares` names whatever actually blocks them, which need
   * not be this symbol at all.
   *
   * Nothing is drawn for a joiner. A bend takes no leg and holds nothing
   * apart, so the panel had only the ways passing through it to show — and,
   * headed by the bend's own name above the connections, read as a connection
   * of its own that the netlist did not list.
   */
  private inspected() {
    if (this.symbol === null) return nothing;
    const crossing = through(this.review!, this.symbol);
    if (crossing.length === 0 || !routes(crossing)) return nothing;
    const pairs = amongst(this.review!, this.symbol);
    return html`
      <section class="symbol">
        <h2>${this.symbol}<span class="count">${count(crossing.length, "transit")}</span></h2>
        <ul class="transits">
          ${crossing.map(
            ({ connection, transit, legs }) => html`
              <li>
                <button
                  class=${this.isChosen(connection, transit) ? "on" : ""}
                  @click=${() => this.choose(connection, transit)}
                >
                  <span class="transit">${transit}</span>
                  <span class="ends">${took(legs)}</span>
                </button>
              </li>
            `,
          )}
        </ul>
        ${pairs.length === 0
          ? nothing
          : html`<ul class="against">${pairs.map((pair) => this.pair(pair))}</ul>`}
      </section>
    `;
  }

  /** A pair through the selected symbol. The legs it names are the symbol's
   *  own, which is what makes the verdict checkable by looking — so they are
   *  left off where the symbol has none, a joiner being passed through. */
  private pair(pair: Pair) {
    const legs = pair.legs.every((taken) => taken.every((leg) => leg === WHOLE))
      ? ""
      : `, on ${pair.legs.map(took).join(" / ")}`;
    return html`
      <li class=${pair.concurrent ? "with" : "without"}>
        <span>${pair.one} + ${pair.two}</span>
        <span class="why">
          ${pair.concurrent
            ? `runs together${legs}`
            : `shares ${pair.shared.join(", ") || "the way"}${legs}`}
        </span>
      </li>
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

function count(many: number, what: string): string {
  return `${many} ${what}${many === 1 ? "" : "s"}`;
}

/** The legs a transit takes through a symbol, as words. A joiner has none of
 *  its own; the way goes straight through it. */
function took(legs: string[]): string {
  return legs.map((leg) => (leg === WHOLE ? "through" : leg)).join(", ");
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-netlist": TcNetlist;
  }
}
