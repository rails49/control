/**
 * The request list: every request the dispatcher holds, in the order it serves
 * them, with a cancel on each and a drag to reorder the waiting ones
 * ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md),
 * [#829](https://github.com/rails49/control/issues/829)).
 *
 * It sits under the roster in the run view's left pane. A row is the train,
 * where the request starts, where it ends, and `waiting` or `underway`, and,
 * under them, which train it waits for where the dispatcher refused it a
 * launch or a move (#1114). An underway row whose cancel the dispatcher holds
 * says where the train stops in place of `underway`, and its cancel is off
 * until the row goes (#1115): the train runs on into that block first.
 *
 * It works nothing out. The rows arrive as data (`Panel.requestList`), and
 * what a drag asks is `model/requests.ts`'s answer: this says which row was
 * let go where, and raises `request-reordered` only where that answer is a
 * move, so a refused drag sends nothing and the row stays where it was.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { reordering, type RequestRow } from "../model/requests.js";
import { requestsStyles } from "./tc-requests.styles.js";

/** A cancel pressed: the request to end. */
export interface RequestCancel {
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

  /** Whether a press means anything: only a joined session has a dispatcher
   *  to send a cancel or a move to. */
  @property({ type: Boolean }) live = false;

  /** The row being dragged, so it reads as picked up. */
  @state() private held: string | null = null;

  override render() {
    return html`
      <h2>Requests</h2>
      ${this.requests.length === 0
        ? html`<p class="hint">no requests</p>`
        : html`
            <ul>
              ${this.requests.map((request) => this.row(request))}
            </ul>
          `}
    `;
  }

  /** One request. A waiting row can be picked up; an underway one cannot,
   *  having started. Both can be cancelled, once. */
  private row(request: RequestRow) {
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
        <span class="train" title=${train}>${train}</span>
        <span class="state">${said}</span>
        <span class="way">${ends(from)} → ${ends(to)}</span>
        ${(note ?? []).map((sentence) => html`<span class="note">${sentence}</span>`)}
        ${this.live
          ? html`<button
              class="cancel"
              title=${cancelling === undefined ? "Cancel request" : "already cancelling"}
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

  /** Row `id` let go at position `at`: one `request-reordered`, or nothing
   *  where the drag is refused or moves nothing (`model/requests.ts`). */
  move(id: string, at: number): void {
    const wanted = reordering(this.requests, id, at);
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
      new CustomEvent<RequestCancel>("request-cancelled", {
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
