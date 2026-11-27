/**
 * A row of the timetable list (`tc-requests`, #1393): its cells, and the
 * "waits for" line under a refused request. The list draws the table, its
 * column headings and the open row, and puts these in each row.
 *
 * The cells are Time, Train, To, Dwell, Description, State and the action,
 * in that order, each a `span` named for its column (`.time`, `.train`,
 * `.way`, `.dwell`, `.description`, `.state`, `.action`). A row has all
 * seven, empty where it has nothing for one.
 *
 * - **Time, Dwell, Description**: the entry's, on an entry's row and on a
 *   request an entry went out as. A request no entry went out as has none.
 * - **Train**: the row's train, after a dot in its colour (`train-dot.ts`,
 *   #1410).
 * - **To**: `→ <ends>` for an entry, `turn` for a turn-round,
 *   `<from> → <to>` for a request, and `→ <to>` for a chained request whose
 *   earlier one is no longer listed. Ends are joined with `, `.
 * - **State**: the entry's state, or the request's `waiting` or `underway`,
 *   and `cancelling — stops in <block>` while the dispatcher holds its cancel
 *   (#1115).
 * - **Action**, on a request where a press means anything: "arrived" on an
 *   underway row where the list is arrivable (#1323), then the cancel, off
 *   while a cancel is held. A press on either does not reach the row, so it
 *   picks nothing up.
 *
 * The note is a line per sentence of the request's `note` (#1114), and
 * nothing on any other row.
 */

import { html, nothing, type TemplateResult } from "lit";

import type { TrainColour } from "../colour.generated.js";
import type { Entry, ListRow } from "../model/timetable.js";
import { dot } from "./train-dot.js";

/** What a row's buttons need from the list. */
export interface RowActions {
  /** Whether a press means anything: only a joined session has a dispatcher
   *  to send it to. */
  live: boolean;
  /** Whether an underway row offers "arrived" (#1323). */
  arrivable: boolean;
  arrived(id: string): void;
  cancel(id: string): void;
}

/** The row's seven cells, its train's dot in `colour`: the train's colour in
 *  the trains read, `undefined` for a train missing from it. */
export function cells(
  { entry, state, request }: ListRow,
  actions: RowActions,
  colour: TrainColour | undefined,
): TemplateResult {
  const said =
    request === undefined
      ? state
      : request.cancelling === undefined
        ? request.state
        : `cancelling — stops in ${request.cancelling}`;
  const to = request === undefined ? way(entry!) : `${start(request.from)}→ ${ends(request.to)}`;
  return html`
    <span class="time">${entry?.at}</span>
    <span class="train">${dot(colour)}${request?.train ?? entry?.train}</span>
    <span class="way">${to}</span>
    <span class="dwell">${entry?.dwell ? `${entry.dwell} min` : nothing}</span>
    <span class="description">${entry?.description}</span>
    <span class="state">${said}</span>
    <span class="action">${request === undefined ? nothing : buttons(request, actions)}</span>
  `;
}

/** The "waits for" line under a refused request, a line per sentence. */
export function note({ request }: ListRow): TemplateResult {
  return html`${(request?.note ?? []).map((sentence) => html`<span class="note">${sentence}</span>`)}`;
}

/** Where an entry goes. */
function way(entry: Entry): string {
  return entry.to === undefined ? "turn" : `→ ${ends(entry.to)}`;
}

/** Where a request starts, and the space before its arrow; nothing where it
 *  has no start. */
function start(from: readonly string[]): string {
  return from.length === 0 ? "" : `${ends(from)} `;
}

function ends(at: readonly string[]): string {
  return at.join(", ");
}

/** A request's "arrived" and cancel, where a press means anything. */
function buttons(
  { id, state, cancelling }: NonNullable<ListRow["request"]>,
  { live, arrivable, arrived, cancel }: RowActions,
) {
  if (!live) return nothing;
  const stop = (event: PointerEvent) => event.stopPropagation();
  return html`
    ${arrivable && state === "underway"
      ? html`<button
          class="arrived"
          aria-label="Train has arrived"
          @pointerdown=${stop}
          @click=${() => arrived(id)}
        >
          arrived
        </button>`
      : nothing}
    <button
      class="cancel"
      aria-label=${cancelling === undefined ? "Cancel request" : "already cancelling"}
      ?disabled=${cancelling !== undefined}
      @pointerdown=${stop}
      @click=${() => cancel(id)}
    >
      ×
    </button>
  `;
}
