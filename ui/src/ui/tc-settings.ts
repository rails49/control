/**
 * The settings dialog: what belongs to all of control rather than to one
 * railroad (#733, #737,
 * [ADR-0072](../../../docs/adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).
 *
 * Three tabs, the dialog opening on the first each time (#899). **Railroad**
 * lists what the store holds, the loaded one ticked, and a press on another
 * asks for it: it publishes `railroad_wanted` through
 * the app and stops there, and the tick moves when the layout's row names the
 * new railroad, which is the only thing that loads one (ADR-0060). The dialog
 * stays open, so a person sees the answer come back. Beneath the list a name
 * and two presses make a railroad (decision 3): **New** writes an empty
 * drawing under the name — no roster and no script, a railroad with neither
 * being an ordinary one — and **Copy loaded as…** has the store copy every
 * document of the loaded railroad under it (#729); each then asks for what
 * it wrote, the same way a press on the list does. **Backup** is the one
 * press that opens `tc-backup`, wearing the band note's words where backup
 * has something to say. **Shutdown** turns the box off (#745), and is drawn only
 * where the installation says this box can be: it is asked each time the
 * dialog opens, and the rest of the dialog does not wait on it. The press asks
 * once more before anything is sent, and then says to unplug the box once its
 * lights go out.
 *
 * It is a dialog and not a view: a view shows or edits the loaded railroad,
 * and this chooses which one that is (ADR-0072, decision 1).
 *
 * **It decides nothing.** Why the Railroad tab or the Shutdown tab is refused
 * is `model/settings.ts`, and what is loaded is the row's; the app hands in
 * the row and the power. Whether a name will do is `nameTrouble`'s, as it is for the editor, and
 * a write is refused by the store in its own words (`said`): the dialog shows
 * whichever refused and asks for nothing, so nothing is loaded that was not
 * written.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { lookTheme } from "@rails49/look";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";
import "@shoelace-style/shoelace/dist/components/tab/tab.js";
import "@shoelace-style/shoelace/dist/components/tab-group/tab-group.js";
import "@shoelace-style/shoelace/dist/components/tab-panel/tab-panel.js";

import { emptyDrawing, nameTrouble } from "../model/drawing.js";
import { canTurnOff, turnOff } from "../model/box.js";
import { boxRefusal, copyRefusal, refusal } from "../model/settings.js";
import { copyRailroad, said, saveDrawing } from "../model/store.js";
import type { Power } from "../model/trace.js";
import { settingsStyles } from "./tc-settings.styles.js";

/** What the dialog says where the drawing a load would discard could not be
 *  saved first; the band's trouble chip says why (ADR-0085). */
const UNSAVED = "the drawing could not be saved, so nothing was loaded";

@customElement("tc-settings")
export class TcSettings extends LitElement {
  static override styles = [lookTheme, settingsStyles];

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

  /** What a load would discard, in `Railroad.unsaved`'s words
   *  (`model/railroad.ts`), `null` while nothing is unsaved. The drawing is
   *  not among it: `saving` saves that before a load (ADR-0085). */
  @property({ attribute: false }) unsaved: string | null = null;

  /** Asked before a pick, New or Copy loaded as…: the drawing saved where a
   *  save is owed, answering whether nothing is left unsaved. Where something
   *  is, nothing is loaded and nothing written (ADR-0085, decision 1). */
  @property({ attribute: false }) saving: () => Promise<boolean> = () =>
    Promise.resolve(true);

  /** What backup has to say without being asked, in the band note's words,
   *  `null` where it says nothing (`model/commands.ts`). */
  @property({ attribute: false }) backup: string | null = null;

  /** The name typed for a railroad to make, as typed. */
  @state() private name = "";

  /** What the last New or Copy was refused with — a name that will not do,
   *  in `nameTrouble`'s words, or a write, in the store's — and `null` once
   *  one has gone through or the name is typed at again. */
  @state() private wrong: string | null = null;

  /** Whether a write is out: one at a time, so a second press cannot ask for
   *  a railroad the first is still writing. */
  @state() private writing = false;

  /** Whether the installation said this box can be turned off, asked each
   *  time the dialog opens and no until it answers. */
  @state() private canTurnOff = false;

  /** Where turning the box off has got to: not pressed, asking once more,
   *  the request out, or the box going. */
  @state() private turning: "idle" | "asking" | "sending" | "going" = "idle";

  /** What the installation refused the last request with, or what kept it
   *  from arriving, `null` where nothing did. */
  @state() private refusedOff: string | null = null;

  override willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("open") && this.open) {
      this.canTurnOff = false;
      if (this.turning !== "sending") this.turning = "idle";
      this.refusedOff = null;
      void canTurnOff().then((can) => {
        this.canTurnOff = can;
      });
    }
  }

  override render() {
    if (!this.open) return nothing;
    // Closed draws nothing, so each opening makes the tabs afresh, Railroad
    // the one shown.
    return html`
      <look-dialog open label="Settings" @sl-after-hide=${this.close}>
        <sl-tab-group>
          <sl-tab slot="nav" panel="railroad" active>Railroad</sl-tab>
          <sl-tab slot="nav" panel="backup">Backup</sl-tab>
          ${this.canTurnOff ? html`<sl-tab slot="nav" panel="shutdown">Shutdown</sl-tab>` : nothing}
          <sl-tab-panel name="railroad" active>${this.railroads()}</sl-tab-panel>
          <sl-tab-panel name="backup">
            <div class="backup">
              <sl-button @click=${() => this.say("backup-wanted")}>Backup…</sl-button>
              ${this.backup === null ? nothing : html`<span class="note">${this.backup}</span>`}
            </div>
          </sl-tab-panel>
          ${this.canTurnOff
            ? html`<sl-tab-panel name="shutdown">
                <div class="shutdown">${this.shutdown()}</div>
              </sl-tab-panel>`
            : nothing}
        </sl-tab-group>
        <sl-button slot="footer" @click=${this.close}>Close</sl-button>
      </look-dialog>
    `;
  }

  /**
   * One button per railroad, the loaded one ticked, and beneath them the name
   * field with New and Copy loaded as…. Where the tab is refused the list
   * and both presses are dead and say why once beneath the list, because a
   * list that is dead and silent reads as an app that is broken; Copy alone
   * is dead with nothing loaded, and says so under the presses. A press on
   * the loaded one asks for nothing (#101): the app would throw away
   * whatever has been drawn since when the row came back.
   *
   * A store listing no railroad still offers New: that is the box a first
   * railroad is made on (ADR-0072, decision 6).
   */
  private railroads() {
    const refused = refusal(this.railroad, this.power, this.unsaved);
    const copyRefused = copyRefusal(this.railroad, this.power, this.unsaved);
    const unnamed = this.name.trim() === "";
    return html`
      ${this.drawings.length === 0
        ? html`<p class="hint">the store lists no railroad</p>`
        : html`<ul class="railroads">
            ${this.drawings.map(
              (one) => html`
                <li>
                  <button
                    class=${one === this.railroad ? "loaded" : ""}
                    ?disabled=${refused !== null}
                    @click=${() => void this.wanting(one)}
                  >
                    <span class="tick">${one === this.railroad ? "✓" : ""}</span>
                    <span class="label">${one}</span>
                  </button>
                </li>
              `,
            )}
          </ul>`}
      ${refused === null ? nothing : html`<p class="hint refused">${refused}</p>`}
      <div class="making">
        <sl-input
          class="name"
          label="Name"
          size="small"
          value=${this.name}
          @sl-input=${(event: Event) => {
            this.name = (event.target as HTMLInputElement).value;
            this.wrong = null;
          }}
        ></sl-input>
        <sl-button
          class="new"
          size="small"
          ?disabled=${refused !== null || unnamed || this.writing}
          @click=${() => void this.making(refused, (name) => saveDrawing(emptyDrawing(name)))}
        >
          New
        </sl-button>
        <sl-button
          class="copy"
          size="small"
          ?disabled=${copyRefused !== null || unnamed || this.writing}
          @click=${() =>
            void this.making(copyRefused, (name) => copyRailroad(this.railroad!, name))}
        >
          Copy loaded as…
        </sl-button>
      </div>
      ${copyRefused === null || refused !== null
        ? nothing
        : html`<p class="hint copy">${copyRefused}</p>`}
      ${this.wrong === null ? nothing : html`<p class="hint wrong">${this.wrong}</p>`}
    `;
  }

  /**
   * The Shutdown tab. **Turn the box off…** is dead while the rule refuses or a
   * request is out, with the rule's reason beneath; pressed, it gives way to
   * what turning off costs and **Turn off** and **Cancel**. Once the request
   * is taken the tab says to unplug the box and offers no press.
   */
  private shutdown() {
    if (this.turning === "going") {
      return html`<p class="hint">The box is turning off. Unplug it once its lights go out.</p>`;
    }
    if (this.turning === "asking") {
      return html`
        <p class="asking">
          Every app on this box stops, and starting it again takes a person at the box.
        </p>
        <div class="presses">
          <sl-button class="off" size="small" variant="danger" @click=${this.turningOff}>
            Turn off
          </sl-button>
          <sl-button
            class="cancel"
            size="small"
            @click=${() => {
              this.turning = "idle";
            }}
          >
            Cancel
          </sl-button>
        </div>
      `;
    }
    const refused = boxRefusal(this.power);
    return html`
      <sl-button
        class="turn"
        ?disabled=${refused !== null || this.turning === "sending"}
        @click=${() => {
          this.refusedOff = null;
          this.turning = "asking";
        }}
      >
        Turn the box off…
      </sl-button>
      ${refused === null ? nothing : html`<p class="hint">${refused}</p>`}
      ${this.refusedOff === null ? nothing : html`<p class="hint wrong">${this.refusedOff}</p>`}
    `;
  }

  /** **Turn off** was pressed. The rule is read again, as `wanting` reads
   *  `refusal` again, so power switched on since the first press sends
   *  nothing. */
  private async turningOff(): Promise<void> {
    this.turning = "idle";
    if (boxRefusal(this.power) !== null) return;
    this.turning = "sending";
    const refused = await turnOff();
    this.refusedOff = refused;
    this.turning = refused === null ? "going" : "idle";
  }

  /** A railroad was pressed. The dialog says which is wanted and stops there
   *  — the bus is what loads it, and the app is what carries the press. */
  private async wanting(name: string): Promise<void> {
    if (name === this.railroad) return;
    if (refusal(this.railroad, this.power, this.unsaved) !== null) return;
    if (!(await this.saving())) {
      this.wrong = UNSAVED;
      return;
    }
    this.wanted(name);
  }

  /**
   * New or Copy loaded as… was pressed: `write` is which, and `refused` is
   * why that one is dead, re-read as `wanting` re-reads the list's. The name
   * is checked against the list first, as the editor checks it
   * (`nameTrouble`), so a taken name is refused in the same words wherever it
   * is typed and the store is not asked; a name the list did not have but the
   * store does — made on another page since the dialog opened — is the
   * store's to refuse, and its words are shown. Only a write that went
   * through asks for the railroad, so what is loaded is always something that
   * exists. Copy's `from` is the row's railroad, which `copyRefusal` has
   * seen to be a name by the time the press is live.
   */
  private async making(
    refused: string | null,
    write: (name: string) => Promise<void>,
  ): Promise<void> {
    const name = this.name.trim();
    if (refused !== null || name === "" || this.writing) return;
    const trouble = nameTrouble(name, this.drawings);
    if (trouble !== null) {
      this.wrong = trouble;
      return;
    }
    this.writing = true;
    try {
      if (!(await this.saving())) {
        this.wrong = UNSAVED;
        return;
      }
      await write(name);
    } catch (failure) {
      this.wrong = said(failure);
      return;
    } finally {
      this.writing = false;
    }
    this.wrong = null;
    this.name = "";
    this.wanted(name);
  }

  private wanted(name: string): void {
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
