/**
 * The dialog one of the timetable menu's four rows opens
 * ([#1357](https://github.com/rails49/control/issues/1357)).
 *
 * - **New** asks for a name and raises `timetable_wanted` with it and
 *   `new: true`.
 * - **Rename** asks for a name and raises `timetable_rename_wanted`. A name
 *   the store lists is refused here: the scheduler would drop the gesture.
 * - **Load** lists the names the store has for the railroad. A press on one
 *   reads that document from the store first. Where the store refuses it,
 *   the dialog says what the store said and raises nothing. Otherwise it
 *   raises `timetable_wanted` with the name.
 * - **Delete** lists the same names less the loaded one. A press on one asks
 *   "Delete <name>?", and only its Delete sends the store the `DELETE`.
 *
 * A name is checked as the timetable document checks it (`nameRefused` in
 * `model/timetable.ts`), and a name that is refused raises nothing. New and
 * Load raise nothing while track power is on: the scheduler would drop them.
 *
 * `tc-timetable-controls` makes one each time a row is chosen and takes it
 * away at `timetable-dialog-closed`, so each starts with nothing typed and
 * the store's list read again.
 *
 * @fires timetable-wanted - `CustomEvent<Frame>`: the gesture to publish.
 * @fires timetable-dialog-closed - the dialog is done with.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@rails49/look";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";

import { deleteTimetable, listTimetables, readTimetable, said } from "../model/store.js";
import { nameRefused, powered, type Timetable } from "../model/timetable.js";
import {
  timetableRenameWanted,
  timetableWanted,
  type Frame,
  type Power,
} from "../model/trace.js";
import { timetableDialogStyles } from "./tc-timetable-dialog.styles.js";

/** The menu row a dialog is for. */
export type Asked = "new" | "load" | "rename" | "delete";

@customElement("tc-timetable-dialog")
export class TcTimetableDialog extends LitElement {
  static override styles = timetableDialogStyles;

  /** Which row was chosen. */
  @property({ attribute: false }) asked: Asked = "new";

  /** The loaded timetable, `null` for none. */
  @property({ attribute: false }) timetable: Timetable | null = null;

  /** The railroad whose timetables the store is asked for. */
  @property({ attribute: false }) railroad = "";

  /** Track power as the layout last said it, `null` before it has. */
  @property({ attribute: false }) power: Power | null = null;

  /** The name typed for New or Rename, as typed. */
  @state() private typed = "";

  /** The names the store lists, `null` until it has answered. */
  @state() private names: readonly string[] | null = null;

  /** The name Delete asks about, `null` until one is pressed. */
  @state() private doomed: string | null = null;

  /** What the store last refused with, or why a gesture was not raised. */
  @state() private trouble: string | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    if (this.asked !== "new") void this.list();
  }

  override render() {
    if (this.asked === "new" || this.asked === "rename") return this.naming(this.asked);
    return this.doomed === null ? this.picking(this.asked) : this.confirming(this.doomed);
  }

  /** New and Rename: a name, checked as it is typed. */
  private naming(asked: "new" | "rename") {
    const name = this.typed.trim();
    const refused = this.refusal(asked, name);
    const doing = asked === "new" ? "New" : "Rename";
    return html`
      <look-dialog
        open
        size="small"
        label=${asked === "new" ? "New timetable" : `Rename ${this.timetable?.name ?? ""}`}
        @sl-after-hide=${this.close}
      >
        <sl-input
          class="name"
          label="Name"
          size="small"
          value=${this.typed}
          @sl-input=${(event: Event) => {
            this.typed = (event.target as HTMLInputElement).value;
          }}
        ></sl-input>
        ${this.line(name === "" ? null : refused)}
        <sl-button slot="footer" class="cancel" @click=${this.close}>Cancel</sl-button>
        <sl-button
          slot="footer"
          variant="primary"
          class="confirm"
          ?disabled=${refused !== null}
          @click=${() => this.name(asked, name)}
        >
          ${doing}
        </sl-button>
      </look-dialog>
    `;
  }

  /** Load and Delete: the store's names, one button each. */
  private picking(asked: "load" | "delete") {
    const loaded = this.timetable?.name;
    const names =
      asked === "load" ? this.names : (this.names?.filter((name) => name !== loaded) ?? null);
    const none = asked === "load" ? "no timetables" : "no timetables to delete";
    return html`
      <look-dialog
        open
        size="small"
        label=${asked === "load" ? "Load a timetable" : "Delete a timetable"}
        @sl-after-hide=${this.close}
      >
        ${names === null
          ? nothing
          : names.length === 0
            ? html`<p class="hint">${none}</p>`
            : html`
                <ul>
                  ${names.map(
                    (name) => html`
                      <li>
                        <button class="pick" @click=${() => this.pick(asked, name)}>
                          ${name}
                        </button>
                      </li>
                    `,
                  )}
                </ul>
              `}
        ${this.line(this.trouble)}
        <sl-button slot="footer" class="cancel" @click=${this.close}>Cancel</sl-button>
      </look-dialog>
    `;
  }

  /** The question Delete asks before it sends anything. */
  private confirming(name: string) {
    return html`
      <look-dialog open size="small" label=${`Delete ${name}?`} @sl-after-hide=${this.close}>
        <p class="hint">The store deletes its file.</p>
        ${this.line(this.trouble)}
        <sl-button slot="footer" class="cancel" @click=${this.close}>Cancel</sl-button>
        <sl-button
          slot="footer"
          variant="danger"
          class="confirm"
          @click=${() => void this.delete(name)}
        >
          Delete
        </sl-button>
      </look-dialog>
    `;
  }

  /** What is wrong, as a line of the dialog. */
  private line(words: string | null) {
    return words === null ? nothing : html`<p class="trouble">${words}</p>`;
  }

  /** Why New or Rename does nothing with `name`, `null` where it goes out. */
  private refusal(asked: "new" | "rename", name: string): string | null {
    if (asked === "new") return nameRefused(name) ?? (powered(this.power) || null);
    return nameRefused(name, this.names ?? []);
  }

  private name(asked: "new" | "rename", name: string): void {
    if (this.refusal(asked, name) !== null) return;
    this.wanted(asked === "new" ? timetableWanted(name, true) : timetableRenameWanted(name));
    this.close();
  }

  private pick(asked: "load" | "delete", name: string): void {
    this.trouble = null;
    if (asked === "load") void this.load(name);
    else this.doomed = name;
  }

  /** The store's names for the railroad, or what it said in place of them. */
  private async list(): Promise<void> {
    try {
      this.names = await listTimetables(this.railroad);
    } catch (failure) {
      this.trouble = said(failure);
    }
  }

  /** The document read from the store, then the scheduler asked to load it.
   *  The scheduler answers a load it drops with nothing, so a document the
   *  store refuses is said here. */
  private async load(name: string): Promise<void> {
    try {
      await readTimetable(this.railroad, name);
    } catch (failure) {
      this.trouble = said(failure);
      return;
    }
    const shut = powered(this.power);
    if (shut !== "") {
      this.trouble = shut;
      return;
    }
    this.wanted(timetableWanted(name));
    this.close();
  }

  private async delete(name: string): Promise<void> {
    try {
      await deleteTimetable(this.railroad, name);
    } catch (failure) {
      this.trouble = said(failure);
      return;
    }
    this.close();
  }

  private wanted(frame: Frame): void {
    this.dispatchEvent(
      new CustomEvent<Frame>("timetable-wanted", {
        detail: frame,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private close = (): void => {
    this.dispatchEvent(new CustomEvent("timetable-dialog-closed"));
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-timetable-dialog": TcTimetableDialog;
  }
}
