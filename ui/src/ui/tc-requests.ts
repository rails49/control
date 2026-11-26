/**
 * The list under the roster: the loaded timetable's entries and every request
 * the dispatcher holds, with a cancel on each request and a drag to reorder
 * the waiting ones
 * ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md),
 * [#829](https://github.com/rails49/control/issues/829),
 * [#1356](https://github.com/rails49/control/issues/1356)).
 *
 * It sits in the run view's pane, under the roster, or beside it where the
 * pane is below the drawing. Its heading is "Timetable" and the loaded
 * timetable's name.
 *
 * With no timetable loaded the rows are the requests, in the order the
 * dispatcher serves them. A request's row is the train,
 * where the request starts, where it ends, and `waiting` or `underway`, and,
 * under them, which train it waits for where the dispatcher refused it a
 * launch or a move (#1114). An underway row whose cancel the dispatcher holds
 * says where the train stops in place of `underway`, and its cancel is off
 * until the row goes (#1115): the train runs on into that block first.
 * While the railroad runs without sensors an underway row also has "arrived"
 * before its cancel, for the person to say the train is in its destination
 * block (#1323).
 *
 * With a timetable loaded the rows are its entries, then the requests no
 * entry went out as (`model/timetable.ts`). An entry that is out while the
 * dispatcher lists its request is that request's row with the entry's time
 * before where it goes. Any other entry is its train, its state, its time
 * and where it goes, "turn" for a turn-round. A row that is ended, rejected, cancelled or
 * skipped is dimmed. A row whose entry has a dwell or a description carries
 * them, and the stylesheet shows them where the list is wide. When a
 * timetable is first drawn the list is scrolled to its first row that is not
 * done, and it is not scrolled again while that timetable stays loaded.
 *
 * It works nothing out. The requests and the timetable arrive as data
 * (`Panel.requestList`, `Panel.timetable`), the rows are `model/timetable.ts`'s
 * answer and so is what a drag asks: this says which row was
 * let go where, and raises `request-reordered` only where that answer is a
 * move, so a refused drag sends nothing and the row stays where it was.
 */

import { LitElement, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type { RequestRow } from "../model/requests.js";
import {
  done,
  listRows,
  moving,
  opening,
  type Entry,
  type EntryState,
  type ListRow,
  type Timetable,
} from "../model/timetable.js";
import { requestsStyles } from "./tc-requests.styles.js";

/** A row's cancel or "arrived" pressed: the request the row shows. */
export interface RequestPress {
  id: string;
}

/** A row let go somewhere else in the list: `reorder_wanted`'s payload. */
export interface RequestReorder {
  id: string;
  before: string | null;
}

@customElement("tc-requests")
export class TcRequests extends LitElement {
  static override styles = requestsStyles;

  /** The requests, in the order the dispatcher serves them. */
  @property({ attribute: false }) requests: readonly RequestRow[] = [];

  /** The loaded timetable, `null` for none. */
  @property({ attribute: false }) timetable: Timetable | null = null;

  /** Whether a press means anything: only a joined session has a dispatcher
   *  to send a cancel or a move to. */
  @property({ type: Boolean }) live = false;

  /** Whether an underway row offers "arrived": only while the railroad runs
   *  without sensors, where the person says the train is in its destination
   *  block (#1323). */
  @property({ type: Boolean }) arrivable = false;

  /** The row being dragged, so it reads as picked up. */
  @state() private held: string | null = null;

  /** The rows drawn, top to bottom. */
  private rows: ListRow[] = [];

  /** The name of the timetable the list was last scrolled for, `null` for
   *  none. */
  private opened: string | null = null;

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("requests") || changed.has("timetable")) {
      this.rows = listRows(this.timetable, this.requests);
    }
  }

  override render() {
    return html`
      ${this.heading()}
      ${this.rows.length === 0
        ? html`<p class="hint">${this.timetable === null ? "no requests" : "no entries"}</p>`
        : html`
            <ul>
              ${this.rows.map(({ entry, state, request }) =>
                request === undefined
                  ? this.entryRow(entry!, state!)
                  : this.requestRow(request, entry),
              )}
            </ul>
          `}
    `;
  }

  /** A timetable drawn for the first time opens at its first row that is not
   *  done. */
  protected override updated(): void {
    const name = this.timetable?.name ?? null;
    if (name === this.opened) return;
    this.opened = name;
    const at = name === null ? null : opening(this.rows);
    if (at === null) return;
    this.renderRoot.querySelectorAll("li")[at]?.scrollIntoView({ block: "start" });
  }

  /** "Timetable", and the loaded timetable's name beside it. */
  private heading() {
    return html`
      <header>
        <h2>Timetable</h2>
        ${this.timetable === null
          ? nothing
          : html`<span class="name">${this.timetable.name}</span>`}
      </header>
    `;
  }

  /** An entry that is not out, or whose request the dispatcher does not
   *  list: its time, its train, where it goes and its state. It is no
   *  request, so it has no cancel and is not picked up. */
  private entryRow(entry: Entry, state: EntryState) {
    return html`
      <li class=${done({ entry, state }) ? "still done" : "still"}>
        <span class="train">${entry.train}</span>
        <span class="state">${state}</span>
        <span class="time">${entry.at}</span>
        <span class="way">${entry.to === undefined ? "turn" : `→ ${ends(entry.to)}`}</span>
        ${this.more(entry)}
      </li>
    `;
  }

  /** One request, with the time of the entry it went out as where there is
   *  one. A waiting row can be picked up; an underway one cannot,
   *  having started. Both can be cancelled, once. An underway one can be
   *  said to have arrived where the list is `arrivable`. */
  private requestRow(request: RequestRow, entry: Entry | undefined) {
    const { id, train, from, to, state, note, cancelling } = request;
    const pickable = this.live && state === "waiting";
    const said = cancelling === undefined ? state : `cancelling — stops in ${cancelling}`;
    return html`
      <li
        data-id=${id}
        class=${[state, this.held === id ? "held" : "", pickable ? "" : "still"]
          .filter(Boolean)
          .join(" ")}
        @pointerdown=${(event: PointerEvent) => this.pick(event, request)}
        @pointerup=${(event: PointerEvent) => this.drop(event, id)}
        @pointercancel=${() => (this.held = null)}
      >
        <span class="train">${train}</span>
        <span class="state">${said}</span>
        ${entry === undefined ? nothing : html`<span class="time">${entry.at}</span>`}
        <span class="way">${ends(from)} → ${ends(to)}</span>
        ${entry === undefined ? nothing : this.more(entry)}
        ${(note ?? []).map((sentence) => html`<span class="note">${sentence}</span>`)}
        ${this.live && this.arrivable && state === "underway"
          ? html`<button
              class="arrived"
              aria-label="Train has arrived"
              @pointerdown=${(event: PointerEvent) => event.stopPropagation()}
              @click=${() => this.arrived(id)}
            >
              arrived
            </button>`
          : nothing}
        ${this.live
          ? html`<button
              class="cancel"
              aria-label=${cancelling === undefined ? "Cancel request" : "already cancelling"}
              ?disabled=${cancelling !== undefined}
              @pointerdown=${(event: PointerEvent) => event.stopPropagation()}
              @click=${() => this.cancel(id)}
            >
              ×
            </button>`
          : nothing}
      </li>
    `;
  }

  /** An entry's dwell and description, where it has them. The stylesheet
   *  shows them only where the list is wide. */
  private more({ dwell, description }: Entry) {
    return html`
      ${dwell ? html`<span class="dwell">dwell ${dwell} min</span>` : nothing}
      ${description ? html`<span class="description">${description}</span>` : nothing}
    `;
  }

  /** A press on a waiting row takes hold of it. The row captures the pointer,
   *  so the release lands here wherever it happens. */
  private pick(event: PointerEvent, request: RequestRow): void {
    if (event.button !== 0 || !this.live || request.state !== "waiting") return;
    (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
    this.held = request.id;
  }

  /** The release: the row lands in front of the first row whose middle is
   *  below the pointer, or at the end below them all. */
  private drop(event: PointerEvent, id: string): void {
    if (this.held !== id) return;
    this.held = null;
    const boxes = [...this.renderRoot.querySelectorAll("li")].map((row) =>
      row.getBoundingClientRect(),
    );
    const below = boxes.findIndex((box) => event.clientY < box.top + box.height / 2);
    this.move(id, below === -1 ? boxes.length : below);
  }

  /** The row of request `id` let go at position `at` of the list: one
   *  `request-reordered`, or nothing where the drag is refused or moves
   *  nothing (`model/timetable.ts`). */
  move(id: string, at: number): void {
    const wanted = moving(this.rows, this.requests, id, at);
    if (wanted === null) return;
    this.dispatchEvent(
      new CustomEvent<RequestReorder>("request-reordered", {
        detail: { id, before: wanted.before },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private cancel(id: string): void {
    this.dispatchEvent(
      new CustomEvent<RequestPress>("request-cancelled", {
        detail: { id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private arrived(id: string): void {
    this.dispatchEvent(
      new CustomEvent<RequestPress>("request-arrived", {
        detail: { id },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

/** A set of block ends in words: one end as itself, several joined, and none
 *  as a dash — a chained request whose earlier one is no longer listed. */
function ends(at: readonly string[]): string {
  return at.length === 0 ? "—" : at.join(", ");
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-requests": TcRequests;
  }
}
