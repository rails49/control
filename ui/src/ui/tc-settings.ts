/**
 * The settings dialog: what belongs to all of control rather than to one
 * railroad (#733,
 * [ADR-0072](../../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).
 *
 * Two parts. **Railroad** lists what the store holds, the loaded one ticked,
 * and a press on another asks for it: it publishes `railroad_wanted` through
 * the app and stops there, and the tick moves when the layout's row names the
 * new railroad, which is the only thing that loads one (ADR-0060). The dialog
 * stays open, so a person sees the answer come back. **Backup** is the one
 * press that opens `tc-backup`, wearing the band note's words where backup has
 * something to say.
 *
 * It is a dialog and not a view: a view shows or edits the loaded railroad,
 * and this chooses which one that is (ADR-0072, decision 1).
 *
 * **It decides nothing.** Why the railroad part is refused is
 * `model/settings.ts`, and what is loaded is the row's; the app hands both in.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";

import { refusal } from "../model/settings.js";
import type { Power } from "../model/trace.js";
import { settingsStyles } from "./tc-settings.styles.js";

@customElement("tc-settings")
export class TcSettings extends LitElement {
  static override styles = settingsStyles;

  /** Whether the dialog is up. Closed is nothing to draw, as `tc-backup`'s
   *  `backing` is. */
  @property({ type: Boolean }) open = false;

  /** The railroads there are to load, as the store lists them. */
  @property({ attribute: false }) drawings: readonly string[] = [];

  /** The loaded railroad as `RunStatus.railroad` has it: `null` while the
   *  layout has not said, `""` where it says none is loaded (#727). */
  @property({ attribute: false }) railroad: string | null = null;

  /** The supply as the run reads it, `null` with no session joined. */
  @property({ attribute: false }) power: Power | null = null;

  /** What a load would discard, in the words of the app's discard question,
   *  `null` while nothing is unsaved. */
  @property({ attribute: false }) unsaved: string | null = null;

  /** What backup has to say without being asked, in the band note's words,
   *  `null` where it says nothing (`model/commands.ts`). */
  @property({ attribute: false }) backup: string | null = null;

  override render() {
    if (!this.open) return nothing;
    return html`
      <sl-dialog open label="Settings" @sl-after-hide=${this.close}>
        <h3>Railroad</h3>
        ${this.railroads()}
        <h3>Backup</h3>
        <div class="backup">
          <sl-button @click=${() => this.say("backup-wanted")}>Backup…</sl-button>
          ${this.backup === null ? nothing : html`<span class="note">${this.backup}</span>`}
        </div>
        <sl-button slot="footer" @click=${this.close}>Close</sl-button>
      </sl-dialog>
    `;
  }

  /**
   * One button per railroad, the loaded one ticked. Where the part is
   * refused the list is dead and says why beneath, because a list that is
   * dead and silent reads as an app that is broken. A press on the loaded
   * one asks for nothing (#101): the app would throw away whatever has been
   * drawn since when the row came back.
   */
  private railroads() {
    if (this.drawings.length === 0) {
      return html`<p class="hint">the store lists no railroad</p>`;
    }
    const refused = refusal(this.railroad, this.power, this.unsaved);
    return html`
      <ul class="railroads">
        ${this.drawings.map(
          (one) => html`
            <li>
              <button
                class=${one === this.railroad ? "loaded" : ""}
                ?disabled=${refused !== null}
                @click=${() => this.wanting(one)}
              >
                <span class="tick">${one === this.railroad ? "✓" : ""}</span>
                <span class="label">${one}</span>
              </button>
            </li>
          `,
        )}
      </ul>
      ${refused === null ? nothing : html`<p class="hint refused">${refused}</p>`}
    `;
  }

  /** A railroad was pressed. The dialog says which is wanted and stops there
   *  — the bus is what loads it, and the app is what carries the press. */
  private wanting(name: string): void {
    if (name === this.railroad) return;
    if (refusal(this.railroad, this.power, this.unsaved) !== null) return;
    this.dispatchEvent(
      new CustomEvent<string>("railroad-wanted", {
        detail: name,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private close(): void {
    this.say("settings-closed");
  }

  private say(what: "backup-wanted" | "settings-closed"): void {
    this.dispatchEvent(new CustomEvent<void>(what, { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-settings": TcSettings;
  }
}
