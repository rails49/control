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
 * timetable's name, and it stays in view: the rows scroll under it.
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
 * A tap on an entry's row opens it
 * ([#1358](https://github.com/rails49/control/issues/1358)): `tc-entry` is
 * drawn under the row's lines, with the entry's time, dwell and description
 * and a Delete. One row is open at a time and a tap on the open row closes
 * it. A request no entry went out as does not open. Which row is open after
 * a tap, after a change and when the scheduler says new rows is
 * `model/timetable.ts`'s answer (`Opened`). The list is scrolled to a row
 * that opens and to an open row that moves. What the open row asks,
 * `entry-changed`, goes on to the view.
 *
 * The open row's elements are the same ones from the tap that opened it until
 * it closes or another row is tapped, wherever the scheduler's rows put its
 * entry and whether it is the entry's row or its request's. A field in it
 * keeps the focus and the words typed in it while the rows round it change.
 *
 * It works nothing out. The requests and the timetable arrive as data
 * (`Panel.requestList`, `Panel.timetable`), the rows are `model/timetable.ts`'s
 * answer and so are which row is open and what a drag asks: this says which
 * row was tapped and which was let go where, and raises `request-reordered`
 * only where that answer is a move, so a refused drag sends nothing and the
 * row stays where it was.
 */

import { LitElement, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { ifDefined } from "lit/directives/if-defined.js";
import { keyed } from "lit/directives/keyed.js";

import type { RequestRow } from "../model/requests.js";
import {
  asking,
  done,
  followed,
  listRows,
  moving,
  opening,
  placeOf,
  tapped,
  type Entry,
  type EntryState,
  type ListRow,
  type Opened,
  type Timetable,
} from "../model/timetable.js";
import "./tc-entry.js";
import type { EntryChange } from "./tc-entry.js";
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

  /** The entry whose row is open, `null` for none. */
  @state() private open: Opened | null = null;

  /** The open row's place in `rows`, -1 for none. */
  private at = -1;

  /** How many taps on an entry's row there have been. */
  private taps = 0;

  /** The tap that opened the row last scrolled to and the place it had,
   *  `null` for none. */
  private shown: string | null = null;

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("requests") || changed.has("timetable")) {
      this.rows = listRows(this.timetable, this.requests);
      this.open = followed(this.open, this.rows);
    }
    this.at = this.open === null ? -1 : placeOf(this.rows, this.open.entry);
  }

  /** The open row is drawn apart from the rows before and after it, and all
   *  rows with one template: its `li` and its `tc-entry` are kept while rows
   *  are added, taken away or changed round it, and made again only for
   *  another tap. */
  override render() {
    const rows = this.rows;
    const open = rows[this.at];
    const before = open === undefined ? rows : rows.slice(0, this.at);
    const after = open === undefined ? [] : rows.slice(this.at + 1);
    return html`
      ${this.heading()}
      ${rows.length === 0
        ? html`<p class="hint">${this.timetable === null ? "no requests" : "no entries"}</p>`
        : html`
            <ul>
              ${before.map((row) => this.row(row, false))}
              ${open === undefined ? nothing : keyed(this.taps, this.row(open, true))}
              ${after.map((row) => this.row(row, false))}
            </ul>
          `}
    `;
  }

  /** A row that opens, and an open row that moves, is scrolled into the
   *  list. A timetable drawn for the first time opens at its first row that
   *  is not done. */
  protected override updated(): void {
    const shown = this.at === -1 ? null : `${this.taps}/${this.at}`;
    if (shown !== this.shown) {
      this.shown = shown;
      this.renderRoot.querySelector("tc-entry")?.parentElement?.scrollIntoView({
        block: "nearest",
      });
    }
    const name = this.timetable?.name ?? null;
    if (name === this.opened) return;
    this.opened = name;
    const at = name === null ? null : opening(this.rows);
    if (at === null) return;
    this.renderRoot.querySelectorAll("li")[at]?.scrollIntoView({ block: "start" });
  }

  /** "Timetable", and the loaded timetable's name beside it. The run view
   *  puts the heading's controls in the slot (`tc-timetable-controls`). */
  private heading() {
    return html`
      <header>
        <h2>Timetable</h2>
        ${this.timetable === null
          ? nothing
          : html`<span class="name">${this.timetable.name}</span>`}
        <slot name="controls"></slot>
      </header>
    `;
  }

  /**
   * One row.
   *
   * - An entry that is not out, or whose request the dispatcher does not
   *   list: its train, its state, its time and where it goes. It is no
   *   request, so it has no cancel and is not picked up.
   * - A request, with the time of the entry it went out as where there is
   *   one. A waiting row can be picked up; an underway one cannot, having
   *   started. Both can be cancelled, once. An underway one can be said to
   *   have arrived where the list is `arrivable`.
   *
   * `open` draws the entry's fields under the row's lines.
   */
  private row(row: ListRow, open: boolean) {
    const { entry, state, request } = row;
    const pickable = this.live && request?.state === "waiting";
    const classes =
      request === undefined
        ? ["still", done(row) ? "done" : ""]
        : [request.state, this.held === request.id ? "held" : "", pickable ? "" : "still"];
    return html`
      <li
        data-id=${ifDefined(request?.id)}
        class=${classes.filter(Boolean).join(" ")}
        @pointerdown=${(event: PointerEvent) => this.pick(event, request)}
        @pointerup=${(event: PointerEvent) => this.drop(event, request?.id)}
        @pointercancel=${() => (this.held = null)}
        @click=${(event: MouseEvent) => this.tapped(event, entry)}
      >
        ${request === undefined ? this.entryLines(entry!, state!) : this.requestLines(request, entry)}
        ${entry !== undefined && open ? this.fields(entry) : nothing}
        ${request === undefined ? nothing : this.buttons(request)}
      </li>
    `;
  }

  /** The lines of an entry's row: its train, its state, its time and where
   *  it goes, "turn" for a turn-round. */
  private entryLines(entry: Entry, state: EntryState) {
    return html`
      <span class="train">${entry.train}</span>
      <span class="state">${state}</span>
      <span class="time">${entry.at}</span>
      <span class="way">${entry.to === undefined ? "turn" : `→ ${ends(entry.to)}`}</span>
      ${this.more(entry)}
    `;
  }

  /** The lines of a request's row: its train, its state, the time of the
   *  entry it went out as, where it goes from and to, and what it waits for. */
  private requestLines(request: RequestRow, entry: Entry | undefined) {
    const { train, from, to, state, note, cancelling } = request;
    const said = cancelling === undefined ? state : `cancelling — stops in ${cancelling}`;
    return html`
      <span class="train">${train}</span>
      <span class="state">${said}</span>
      ${entry === undefined ? nothing : html`<span class="time">${entry.at}</span>`}
      <span class="way">${ends(from)} → ${ends(to)}</span>
      ${entry === undefined ? nothing : this.more(entry)}
      ${(note ?? []).map((sentence) => html`<span class="note">${sentence}</span>`)}
    `;
  }

  /** A request's "arrived" and cancel, where a press means anything. */
  private buttons({ id, state, cancelling }: RequestRow) {
    return html`
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

  /** The open part of an entry's row (`tc-entry`). A press in it does not
   *  pick the row up. */
  private fields(entry: Entry) {
    return html`<tc-entry
      .entry=${entry}
      @pointerdown=${(event: PointerEvent) => event.stopPropagation()}
      @entry-changed=${this.asked}
    ></tc-entry>`;
  }

  /**
   * A click on a row. On an entry's row it is a tap, and what it opens or
   * closes is `tapped`'s answer (`model/timetable.ts`). It is no tap:
   *
   * - on the row's cancel or "arrived", or in its open part;
   * - where the pointer is off the row. A row that is picked up captures the
   *   pointer, and a browser may send it the click that ends a drag.
   *
   * Every row has this listener, a request's with no entry too, where it
   * opens nothing.
   */
  private tapped(event: MouseEvent, entry: Entry | undefined): void {
    if (entry === undefined) return;
    if ((event.target as Element).closest("button, tc-entry") !== null) return;
    if (!over(event.currentTarget as Element, event)) return;
    this.open = tapped(this.open, entry);
    this.taps += 1;
  }

  /** What the open row asked. The event goes on to the view, which sends
   *  it. */
  private asked(event: CustomEvent<EntryChange>): void {
    this.open = asking(this.open, event.detail.now);
  }

  /** A press on a waiting request's row takes hold of it. The row captures
   *  the pointer, so the release lands here wherever it happens. */
  private pick(event: PointerEvent, request: RequestRow | undefined): void {
    if (event.button !== 0 || !this.live || request?.state !== "waiting") return;
    (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
    this.held = request.id;
  }

  /** The release: the row lands in front of the first row whose middle is
   *  below the pointer, or at the end below them all. */
  private drop(event: PointerEvent, id: string | undefined): void {
    if (id === undefined || this.held !== id) return;
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

/** Whether the pointer is over `row`. */
function over(row: Element, { clientX, clientY }: MouseEvent): boolean {
  const box = row.getBoundingClientRect();
  return (
    box.left <= clientX && clientX <= box.right && box.top <= clientY && clientY <= box.bottom
  );
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-requests": TcRequests;
  }
}
