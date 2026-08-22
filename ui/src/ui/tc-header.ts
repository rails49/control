/**
 * The band across the top of both pages: what is open, and the status that is
 * nobody's mistake.
 *
 * Two things the author is answerable for read here anyway
 * ([ADR-0024](../../../docs/adr/0024-the-drawing-shows-its-own-faults.md)).
 * Whether the drawing derives is coarse enough to belong: it names no fault
 * and counts nothing — the canvas is where you find out where — so it is
 * status beside the rest, not a list of faults creeping back into the band. A
 * name no drawing can wear is the other: it is typed at a prompt that is gone
 * by the time it is refused, and nothing on the canvas is wrong.
 *
 * One component for both pages, because the two facts every page has — what is
 * open and what is wrong outside the drawing — are the same facts. The editor
 * and the panel stay separate entries (vite.config.ts) and separate pages; the
 * band names the page it is on and offers a way to the other, which is the
 * whole of the navigation.
 *
 * It shows status and nothing else. Everything a person presses stays in the
 * row below — the editor's menu bar, the panel's controls (EDITOR.md,
 * PANEL.md) — the unsaved dot included: it is the mark that used to be
 * readable only as the Save button's disabled state, and #85 took that button
 * off the screen entirely.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import { headerStyles } from "./tc-header.styles.js";

/** Which page the band is on. The run view's one source is the bus, so there
 *  is no second one to name (ADR-0038). */
export type Mode = "editor" | "run";

@customElement("tc-header")
export class TcHeader extends LitElement {
  static override styles = headerStyles;

  /** The drawing the page has open, `null` while none is. */
  @property() drawing: string | null = null;

  /** Whether the open drawing holds edits the store has not been given. */
  @property({ type: Boolean }) unsaved = false;

  @property() mode: Mode = "editor";

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

  override render() {
    const editing = this.mode === "editor";
    return html`
      <span class="drawing">${this.drawing ?? "no drawing"}</span>
      ${this.unsaved
        ? html`<span class="unsaved" role="img" title="unsaved" aria-label="unsaved">
            ●
          </span>`
        : nothing}
      <span class="spacer"></span>
      ${this.derives
        ? nothing
        : html`<span class="refused">does not derive</span>`}
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
      ${editing
        ? nothing
        : html`<span class="boundary">
            ${this.boundary === null ? "—" : `boundary ${this.boundary}`}
          </span>`}
      <a class="other" href=${editing ? "/panel.html" : "/"}>
        ${editing ? "run" : "editor"}
      </a>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-header": TcHeader;
  }
}
