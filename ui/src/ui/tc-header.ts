/**
 * The band across the top of both pages: what is open, which mode it is being
 * looked at in, and the status that is nobody's mistake.
 *
 * One component for both pages, because the two facts every page has — what is
 * open and what is wrong outside the drawing — are the same facts. The editor
 * and the panel stay separate entries (vite.config.ts) and separate apps
 * ([ADR-0016](../../../docs/adr/0016-the-panel-is-a-scheduler.md)); the band
 * names the page it is on and offers a way to the other, which is the whole of
 * the navigation.
 *
 * It shows status and nothing else. Everything a person presses stays in the
 * control row below (EDITOR.md, PANEL.md), the unsaved dot included: it is the
 * mark that used to be readable only as the Save button's disabled state, and
 * #85 takes that button off the screen entirely.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import { headerStyles } from "./styles.js";

/** Which page the band is on and, on the panel, which of ADR-0016's two
 *  exclusive sources is feeding it. */
export type Mode = "editor" | "replay" | "live" | "unjoined";

/** What each mode is called on screen. */
const MODES: Record<Mode, string> = {
  editor: "editor",
  replay: "replay",
  live: "live",
  unjoined: "nothing joined",
};

@customElement("tc-header")
export class TcHeader extends LitElement {
  static override styles = headerStyles;

  /** The drawing the page has open, `null` while none is. */
  @property() drawing: string | null = null;

  /** Whether the open drawing holds edits the store has not been given. */
  @property({ type: Boolean }) unsaved = false;

  @property() mode: Mode = "editor";

  /** The trace file a replay is reading, `null` when none is open. */
  @property() trace: string | null = null;

  /** What is wrong outside the drawing — the store not answering, a bridge
   *  that is not there. Never a finding about the drawing itself. */
  @property() trouble: string | null = null;

  /** Whether the bridge is answering. Read only in a live session. */
  @property({ type: Boolean }) linked = false;

  /** The tick the run has reached, `null` before the first one. Read on the
   *  panel only: a drawing is not a run. */
  @property({ type: Number }) tick: number | null = null;

  override render() {
    const editing = this.mode === "editor";
    return html`
      <span class="drawing">${this.drawing ?? "no drawing"}</span>
      ${this.unsaved
        ? html`<span class="unsaved" title="unsaved" aria-label="unsaved">●</span>`
        : nothing}
      <span class="mode">${MODES[this.mode]}</span>
      ${this.trace === null ? nothing : html`<span class="trace">${this.trace}</span>`}
      <span class="spacer"></span>
      ${this.trouble === null
        ? nothing
        : html`<span class="trouble">${this.trouble}</span>`}
      ${this.mode === "live"
        ? html`
            <span class=${`link ${this.linked ? "joined" : "gone"}`}>
              ${this.linked ? "connected" : "not connected"}
            </span>
          `
        : nothing}
      ${editing
        ? nothing
        : html`<span class="tick">${this.tick === null ? "—" : `tick ${this.tick}`}</span>`}
      <a class="other" href=${editing ? "/panel.html" : "/"}>
        ${editing ? "panel" : "editor"}
      </a>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-header": TcHeader;
  }
}
