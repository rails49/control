/**
 * The band across the top: what is true of the whole system
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * Which railroad is loaded and the way to another, whether it holds unsaved
 * edits, whether what the app talks to is answering, and which view is
 * current. The bar below carries what acts on that view's document.
 *
 * The line is *what it is about*, not *whether it is pressable*. The rule this
 * carried — "it shows status and nothing else. Everything a person presses
 * stays in the row below" — was already broken by the navigation link that
 * stood at this end, and it has no answer for track power, which is pressable
 * and is a fact about the whole railroad rather than about a document.
 *
 * Two things the author is answerable for read here anyway
 * ([ADR-0024](../../../docs/adr/0024-the-drawing-shows-its-own-faults.md)).
 * Whether the drawing derives is coarse enough to belong: it names no fault
 * and counts nothing — the canvas is where you find out where — so it is
 * status beside the rest, not a list of faults creeping back into the band. A
 * name no drawing can wear is the other: it is typed at a prompt that is gone
 * by the time it is refused, and nothing on the canvas is wrong.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { VIEWS, type ViewId } from "../model/views.js";
import { ICONS } from "./icons.js";
import { headerStyles } from "./tc-header.styles.js";

@customElement("tc-header")
export class TcHeader extends LitElement {
  static override styles = headerStyles;

  /** The railroad the app has loaded, `null` while none is. */
  @property() drawing: string | null = null;

  /** The railroads there are to load, as the store lists them. */
  @property({ attribute: false }) drawings: readonly string[] = [];

  /** Whether the open drawing holds edits the store has not been given. */
  @property({ type: Boolean }) unsaved = false;

  /** The view that is current, which the toggle at the right end offers a way
   *  out of. */
  @property() view: ViewId = VIEWS[0]!.id;

  /** Whether a session is joined, which is what makes the bridge a thing to
   *  report on at all. */
  @property({ type: Boolean }) joined = false;

  /** What the page could not do — the store not answering, a bridge that is
   *  not there, a name no drawing can wear. Never a fault of the drawing
   *  itself: those are marked where they are (ADR-0024). */
  @property() trouble: string | null = null;

  /** Whether the drawing derives, which is the one thing the band says about
   *  the drawing itself (ADR-0024). The mark names no fault and counts
   *  nothing: the canvas is where you find out where. A page with nothing to
   *  say about derivation leaves it alone and is left clean. */
  @property({ type: Boolean }) derives = true;

  /** Whether the bridge is answering. Read only in a live session. */
  @property({ type: Boolean }) linked = false;

  /** The grant boundary the run has reached, `null` before the first one.
   *  Read on the panel only: a drawing is not a run. */
  @property({ type: Number }) boundary: number | null = null;

  /** Whether the picker's list is down. */
  @state() private picking = false;

  override render() {
    return html`
      ${this.picker()}
      ${this.unsaved
        ? html`<span class="unsaved" role="img" title="unsaved" aria-label="unsaved">
            ●
          </span>`
        : nothing}
      <span class="spacer"></span>
      ${this.health()} ${this.toggle()}
    `;
  }

  /**
   * Whether what the app talks to is answering, and what it could not do.
   *
   * A region rather than a string, with room in it: per-container reachability
   * and eventually the hardware's belong here too, and what fills the slot is
   * the deployment design's (`2a-docker`). What is here today is the store not
   * answering, the bridge on a joined session, how far the run has got, and
   * the one coarse mark the loaded railroad makes about itself.
   */
  private health() {
    return html`
      <div class="health">
        <slot name="health"></slot>
        ${this.derives ? nothing : html`<span class="refused">does not derive</span>`}
        ${this.trouble === null
          ? nothing
          : html`<span class="trouble" title=${this.trouble}>${this.trouble}</span>`}
        ${this.joined
          ? html`
              <span class=${`link ${this.linked ? "joined" : "gone"}`}>
                ${this.linked ? "connected" : "not connected"}
              </span>
            `
          : nothing}
        ${this.boundary === null
          ? nothing
          : html`<span class="boundary">boundary ${this.boundary}</span>`}
      </div>
    `;
  }

  /**
   * Which view is current, and the way to the next one.
   *
   * The views are a list with one current entry (`model/views.ts`). Two of
   * them render as a single icon-button wearing the other one's icon and
   * name, which is what a toggle is; a third makes this a selector, and that
   * is the redesign the list is here to avoid.
   */
  private toggle() {
    const at = VIEWS.findIndex((view) => view.id === this.view);
    const next = VIEWS[(at + 1) % VIEWS.length]!;
    return html`
      <button
        class="view"
        title=${next.label}
        aria-label=${next.label}
        @click=${() =>
          this.dispatchEvent(
            new CustomEvent<ViewId>("view-wanted", {
              detail: next.id,
              bubbles: true,
              composed: true,
            }),
          )}
      >
        ${ICONS[next.id]}
      </button>
    `;
  }

  /**
   * Which railroad is loaded, and the way to another (#167). It is the band's
   * because it is the whole system's: both views are of it, and a menu on one
   * view's bar would be the editor deciding what the run view is looking at.
   *
   * The railroad that is loaded is ticked, and the tick is all that entry is:
   * choosing it closes the list and asks for nothing (#101). Re-reading it
   * would throw away whatever has been drawn since, which is a lot to ask of a
   * click that looks like it does nothing. The rule moves here whole from
   * `File ▸ Open`.
   */
  private picker() {
    const name = this.drawing ?? "no railroad";
    return html`
      ${this.picking
        ? html`<div class="dismiss" @pointerdown=${() => (this.picking = false)}></div>`
        : nothing}
      <div class="picker">
        <button
          class="chosen"
          aria-haspopup="true"
          aria-expanded=${this.picking}
          ?disabled=${this.drawings.length === 0}
          @click=${() => (this.picking = !this.picking)}
        >
          <span class="drawing">${name}</span>
          <span class="more">▾</span>
        </button>
        ${this.picking
          ? html`
              <menu class="drawings">
                ${this.drawings.map(
                  (one) => html`
                    <li>
                      <button @click=${() => this.wanting(one)}>
                        <span class="tick">${one === this.drawing ? "✓" : ""}</span>
                        <span class="label">${one}</span>
                      </button>
                    </li>
                  `,
                )}
              </menu>
            `
          : nothing}
      </div>
    `;
  }

  /** One of the railroads was chosen. The band says which is wanted and stops
   *  there — the shell is what loads it, and what it asks first is the shell's
   *  question too (#137). */
  private wanting(name: string): void {
    this.picking = false;
    if (name === this.drawing) return;
    this.dispatchEvent(
      new CustomEvent<string>("railroad-wanted", {
        detail: name,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-header": TcHeader;
  }
}
