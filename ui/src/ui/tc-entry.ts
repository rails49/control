/**
 * An entry's open row in the list under the roster: its time, its arrival
 * ends, its dwell, its description and a Delete
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1358](https://github.com/rails49/control/issues/1358),
 * [#1386](https://github.com/rails49/control/issues/1386)).
 *
 * `tc-requests` draws it under the row a person tapped. The time is in the
 * time form `[<day>d]HH:MM` (`model/clock.ts`), the arrival ends, To, the
 * document's ends joined by `, ` (`dn_e, up_e.B`), the dwell whole
 * fast-clock minutes and the description text. A turn-round has no To field
 * and no dwell field.
 *
 * A field changed and then left, or Enter pressed in it, raises
 * `entry-changed` with the entry as it reads and as it should read
 * (`model/timetable.ts`, `edited`). Words that are no value for the field, or
 * that change nothing, raise nothing. A time outside the timetable's repeat
 * raises nothing and the row says why under the time, "before the start
 * 06:00" or "after the last minute, 1d05:59" (`outside`), until the next
 * field is changed. Arrival ends that are none, that have an end other than
 * A or B, that name a block the railroad does not have or name a block
 * twice raise nothing, and the row says why under To in the same way
 * (`misnamed`). Delete raises it with no entry to read, and does not ask
 * first.
 *
 * It changes nothing by itself. A field shows what the entry has, and shows
 * the change when the scheduler's row hands this a changed entry (ADR-0035).
 * A field a person has typed in keeps their words until it is left or Enter
 * is pressed, whatever entry this is handed meanwhile, and then goes back to
 * what the entry has.
 *
 * @fires entry-changed - `CustomEvent<EntryChange>`: `entry_wanted`'s payload.
 */

import { LitElement, html, noChange, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { ifDefined } from "lit/directives/if-defined.js";
import { live } from "lit/directives/live.js";

import {
  edited,
  misnamed,
  outside,
  type Entry,
  type Field,
  type Timetable,
} from "../model/timetable.js";
import { entryStyles } from "./tc-entry.styles.js";

/** What an open row asks for: the entry as it reads, and as it should read,
 *  `null` to delete it. */
export interface EntryChange {
  was: Entry;
  now: Entry | null;
}

@customElement("tc-entry")
export class TcEntry extends LitElement {
  static override styles = entryStyles;

  /** The entry, with the document's fields only, as the scheduler's row
   *  lists it. */
  @property({ attribute: false }) entry: Entry | null = null;

  /** The start and the repeat of the timetable the entry is in. */
  @property({ attribute: false }) timetable: Pick<Timetable, "start" | "repeat"> | null = null;

  /** The names of the railroad's blocks. */
  @property({ attribute: false }) blocks: readonly string[] = [];

  /** The field a person has typed in and not yet left, `null` for none. */
  private typing: Field | null = null;

  /** The field last typed in where its words were refused, and why, `null`
   *  for none. */
  private refused: { field: Field; why: string } | null = null;

  override render() {
    const entry = this.entry;
    if (entry === null) return nothing;
    return html`
      <label>
        <span>Time</span>
        ${this.field(entry, "at", entry.at)}
      </label>
      ${this.why("at")}
      ${entry.to === undefined
        ? nothing
        : html`
            <label>
              <span>To</span>
              ${this.field(entry, "to", entry.to.join(", "))}
            </label>
            ${this.why("to")}
            <label>
              <span>Dwell</span>
              ${this.field(entry, "dwell", String(entry.dwell ?? 0), "numeric")}
              <span>min</span>
            </label>
          `}
      <label class="under">
        <span>Description</span>
        ${this.field(entry, "description", entry.description ?? "")}
      </label>
      <button class="delete" @click=${() => this.ask(entry, null)}>Delete</button>
    `;
  }

  /** Why the words typed in `field` were refused, where they were. */
  private why(field: Field) {
    return this.refused?.field === field
      ? html`<p class="refused">${this.refused.why}</p>`
      : nothing;
  }

  /** One field, showing `words`, what the entry has. The field in use is
   *  left as the person has it. */
  private field(entry: Entry, name: Field, words: string, inputmode?: "numeric") {
    return html`<input
      class=${name}
      inputmode=${ifDefined(inputmode)}
      .value=${this.typing === name ? noChange : live(words)}
      @input=${() => {
        this.typing = name;
      }}
      @change=${(event: Event) => this.typed(entry, name, event)}
      @blur=${this.left}
    />`;
  }

  /** A field left, or Enter pressed in it, with its words changed. The field
   *  is drawn again with what the entry has. */
  private typed(entry: Entry, field: Field, event: Event): void {
    const words = (event.target as HTMLInputElement).value;
    const why =
      field === "at" && this.timetable !== null
        ? outside(this.timetable, words)
        : field === "to"
          ? misnamed(this.blocks, words)
          : null;
    this.refused = why === null ? null : { field, why };
    const now = why === null ? edited(entry, field, words) : null;
    this.left();
    if (now !== null) this.ask(entry, now);
  }

  /** No field is in use, and each is drawn again with what the entry has. */
  private left = (): void => {
    this.typing = null;
    this.requestUpdate();
  };

  private ask(was: Entry, now: Entry | null): void {
    this.dispatchEvent(
      new CustomEvent<EntryChange>("entry-changed", {
        detail: { was, now },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-entry": TcEntry;
  }
}
