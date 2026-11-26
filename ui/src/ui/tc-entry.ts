/**
 * An entry's open row in the list under the roster: its time, its dwell, its
 * description and a Delete
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1358](https://github.com/rails49/control/issues/1358)).
 *
 * `tc-requests` draws it under the row a person tapped. The time is `HH:MM`,
 * the dwell whole fast-clock minutes and the description text. A turn-round
 * has no dwell field. The destination is not here: a person deletes the entry
 * and drags again.
 *
 * A field changed and then left, or Enter pressed in it, raises
 * `entry-changed` with the entry as it reads and as it should read
 * (`model/timetable.ts`, `edited`). Words that are no value for the field, or
 * that change nothing, raise nothing. Delete raises it with no entry to read,
 * and does not ask first.
 *
 * It changes nothing by itself. A field goes back to what the entry has as
 * soon as it is left, and shows the change when the scheduler's row hands
 * this a changed entry (ADR-0035).
 *
 * @fires entry-changed - `CustomEvent<EntryChange>`: `entry_wanted`'s payload.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { live } from "lit/directives/live.js";

import { edited, type Entry, type Field } from "../model/timetable.js";
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

  override render() {
    const entry = this.entry;
    if (entry === null) return nothing;
    return html`
      <label>
        <span>Time</span>
        <input
          class="at"
          .value=${live(entry.at)}
          @change=${(event: Event) => this.typed(entry, "at", event)}
        />
      </label>
      ${entry.to === undefined
        ? nothing
        : html`<label>
            <span>Dwell</span>
            <input
              class="dwell"
              inputmode="numeric"
              .value=${live(String(entry.dwell ?? 0))}
              @change=${(event: Event) => this.typed(entry, "dwell", event)}
            />
            <span>min</span>
          </label>`}
      <label class="under">
        <span>Description</span>
        <input
          class="description"
          .value=${live(entry.description ?? "")}
          @change=${(event: Event) => this.typed(entry, "description", event)}
        />
      </label>
      <button class="delete" @click=${() => this.ask(entry, null)}>Delete</button>
    `;
  }

  /** A field left, or Enter pressed in it, with its words changed. The field
   *  is drawn again with what the entry has. */
  private typed(entry: Entry, field: Field, event: Event): void {
    const now = edited(entry, field, (event.target as HTMLInputElement).value);
    this.requestUpdate();
    if (now !== null) this.ask(entry, now);
  }

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
