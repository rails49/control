/**
 * The band across the top: what is true of the whole system
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * Which railroad is loaded and the way to another, whether it holds unsaved
 * edits, whether what the app talks to is answering, and which view is
 * current. The bar below carries what acts on that view's document.
 *
 * The line is *what it is about*, not *whether it is pressable*. The rule this
 * carried — "it shows status and nothing else. Everything a person presses
 * stays in the row below" — was already broken by the navigation link that
 * stood at this end, and it has no answer for track power, which is a fact
 * about the whole railroad rather than about a document. Power reads here as
 * the observation it is (ADR-0041), and ON, STOP and OFF stand beside the
 * reading because they are about the same whole railroad
 * ([ADR-0051](../../../docs/adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)).
 *
 * Two things the author is answerable for read here anyway
 * ([ADR-0024](../../../docs/adr/0024-the-drawing-shows-its-own-faults.md)).
 * Whether the drawing derives is coarse enough to belong: it names no fault
 * and counts nothing — the canvas is where you find out where — so it is
 * status beside the rest, not a list of faults creeping back into the band. A
 * name no drawing can wear is the other: it is typed at a prompt that is gone
 * by the time it is refused, and nothing on the canvas is wrong.
 */

import { LitElement, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import type { Power } from "../model/trace.js";
import { VIEWS, type ViewId } from "../model/views.js";
import { dismissal } from "./dismissal.js";
import { ICONS } from "./icons.js";
import { headerStyles } from "./tc-header.styles.js";

/** What each power value reads as. `stopped` reads as the thing rather than as
 *  the token, because the two ask for different actions: an emergency stop is
 *  cleared, and a supply that is off is switched back on. */
const POWERED: Record<Power, string> = {
  on: "power on",
  stopped: "emergency stop",
  off: "power off",
};

/** The three presses, in the order a hand reaches for them: the one that
 *  starts a railroad, the one that stops it now, and the one that puts it
 *  away. Each names where the supply should stand rather than asking for a
 *  change, so none of them is greyed by the value it would write. */
const SUPPLY: readonly { power: Power; word: string; says: string }[] = [
  { power: "on", word: "ON", says: "give the track power" },
  { power: "stopped", word: "STOP", says: "stop every locomotive where it stands" },
  { power: "off", word: "OFF", says: "drain the run, then remove the supply" },
];

@customElement("tc-header")
export class TcHeader extends LitElement {
  static override styles = headerStyles;

  /** The railroad the app has loaded, `null` while none is. */
  @property() drawing: string | null = null;

  /** The railroads there are to load, as the store lists them. */
  @property({ attribute: false }) drawings: readonly string[] = [];

  /** Whether the loaded railroad holds edits the store has not been given. */
  @property({ type: Boolean }) unsaved = false;

  /** The view that is current, which the selector at the right end marks and
   *  offers a way out of. */
  @property() view: ViewId = VIEWS[0]!.id;

  /** Whether a session is joined, which is what makes the broker a thing to
   *  report on at all. */
  @property({ type: Boolean }) joined = false;

  /** What the app could not do — the store not answering, a broker that is
   *  not there, a name no drawing can wear. Never a fault of the drawing
   *  itself: those are marked where they are (ADR-0024). */
  @property() trouble: string | null = null;

  /** Whether the drawing derives, which is the one thing the band says about
   *  the drawing itself (ADR-0024). The mark names no fault and counts
   *  nothing: the canvas is where you find out where. */
  @property({ type: Boolean }) derives = true;

  /** Whether the drawing is frozen: a train is on the layout, so the editing
   *  view is read-only until it is off it (`model/commands.ts`, ADR-0038).
   *  Said here because it is true of the system rather than of a view — the
   *  editor's dead verbs are what it explains, and it reads in the run view as
   *  what the run is doing to the drawing. */
  @property({ type: Boolean }) frozen = false;

  /** Whether the broker is answering, read only while a session is joined. */
  @property({ type: Boolean }) linked = false;

  /** Seconds the joined session has been on screen, `null` with no session
   *  joined. The session clock: elapsed time on the page's own clock — a
   *  view reads a clock for scenery, never for control (ADR-0009, ADR-0047)
   *  — until a fast clock derived from the railroad's configuration replaces
   *  it. */
  @state() private sessionS: number | null = null;

  private sessionStart = 0;
  private sessionTimer: ReturnType<typeof setInterval> | undefined;

  /** Whether the layout says a train may move at all, `null` with no session
   *  joined ([ADR-0041](../../../docs/adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
   *  It is the band's because it is the whole railroad's, and it says which of
   *  the two ways of standing still it is: an emergency stop is cleared and a
   *  supply is switched back on, which are different actions by a person. */
  @property() power: Power | null = null;

  /** Whether the run view's OFF is waiting on the drain: it has asked the
   *  run to drain and removes the supply when the run reaches `held`
   *  (ADR-0051). A drain that never lands leaves the railroad powered, so the
   *  button says it is still waiting rather than pretending it is done. */
  @property({ type: Boolean }) draining = false;

  /** Whether the picker's list is down. */
  @state() private picking = false;

  override updated(changed: PropertyValues<this>): void {
    if (!changed.has("joined")) return;
    if (this.joined && this.sessionTimer === undefined) {
      this.sessionStart = Date.now();
      this.sessionS = 0;
      this.sessionTimer = setInterval(() => {
        this.sessionS = Math.floor((Date.now() - this.sessionStart) / 1000);
      }, 1000);
    } else if (!this.joined && this.sessionTimer !== undefined) {
      clearInterval(this.sessionTimer);
      this.sessionTimer = undefined;
      this.sessionS = null;
    }
  }

  override disconnectedCallback(): void {
    if (this.sessionTimer !== undefined) clearInterval(this.sessionTimer);
    this.sessionTimer = undefined;
    super.disconnectedCallback();
  }

  override render() {
    return html`
      ${this.picker()}
      ${this.unsaved
        ? html`<span class="unsaved" role="img" title="unsaved" aria-label="unsaved">
            ●
          </span>`
        : nothing}
      <span class="spacer"></span>
      ${this.health()} ${this.supply()} ${this.chooser()}
    `;
  }

  /**
   * Whether what the app talks to is answering, and what it could not do.
   *
   * A region rather than a string, with room in it: per-container reachability
   * and eventually the hardware's belong here too, and what fills the slot is
   * the deployment design's (`2a-docker`). What is here today is the store not
   * answering, the bridge on a joined session, whether the rails have power,
   * how far the run has got, and the one coarse mark the loaded railroad makes
   * about itself.
   */
  private health() {
    return html`
      <div class="health">
        <slot name="health"></slot>
        ${this.derives ? nothing : html`<span class="refused">does not derive</span>`}
        ${this.frozen
          ? html`<span
              class="frozen"
              title="trains are on the layout, so the drawing is read-only"
            >
              drawing frozen
            </span>`
          : nothing}
        ${this.trouble === null
          ? nothing
          : html`<span class="trouble" title=${this.trouble}>${this.trouble}</span>`}
        ${this.joined
          ? html`
              <span class=${`link ${this.linked ? "joined" : "gone"}`}>
                ${this.linked ? "connected" : "not connected"}
              </span>
            `
          : nothing}
        ${this.power === null
          ? nothing
          : html`
              <span class=${`power ${this.power}`}>${POWERED[this.power]}</span>
            `}
        ${this.sessionS === null
          ? nothing
          : html`<span class="session">session ${clocked(this.sessionS)}</span>`}
      </div>
    `;
  }

  /**
   * ON, STOP and OFF: what the whole railroad's supply should be doing
   * (ADR-0051). They stand beside the reading rather than on the bar below,
   * which is the current view's document's — track power is no document's.
   *
   * **One press each and no confirmation.** An emergency stop that asks "are
   * you sure?" is not one, `stopped` is cheap to recover from with the points
   * still where you left them, and returning to `on` releases nothing on its
   * own, so an explicit GO still follows (ADR-0041). None is greyed by the
   * value it would write: each names where the supply should stand, so a
   * press that agrees with where it stands is not a race.
   *
   * **OFF is the drain trigger.** The press asks the run to drain and the
   * supply goes only once the run has settled; while that is outstanding the
   * button says so, because a drain that never lands leaves the railroad
   * powered and the person has to be able to see that. ON is the way out of
   * a wait, which is why the word on it does not change.
   *
   * With no session joined there is no railroad to command, and a broker that
   * is not answering would swallow the press, so the three are drawn only on
   * a joined session and are dead while it is not connected.
   */
  private supply() {
    if (!this.joined) return nothing;
    return html`
      <div class="supply">
        ${SUPPLY.map(({ power, word, says }) => {
          const waiting = power === "off" && this.draining;
          return html`
            <button
              class=${`press ${power}${waiting ? " waiting" : ""}`}
              title=${waiting ? "waiting for the run to drain" : says}
              ?disabled=${!this.linked || waiting}
              @click=${() =>
                this.dispatchEvent(
                  new CustomEvent<Power>("power-wanted", {
                    detail: power,
                    bubbles: true,
                    composed: true,
                  }),
                )}
            >
              ${waiting ? "DRAINING…" : word}
            </button>
          `;
        })}
      </div>
    `;
  }

  /**
   * Which view is current, and the way to each of the others: **a selector**,
   * one icon-button per view with the current one marked.
   *
   * The views are a list with one current entry (`model/views.ts`), and
   * ADR-0038 wrote down what the list is for: two of them render as one
   * icon-button wearing the other's name, which is what a toggle is, and a
   * third makes it a selector. The third is here (#291), so this is that —
   * the redesign the list existed to keep small, and it is small: every view
   * gets a button, and the current one is the one that is marked rather than
   * the one that is missing.
   *
   * The current view's own button is live and asks for the view it is
   * already showing. Nothing happens — the app ignores a switch to the view
   * it holds — and a control whose only dead button is the one under the
   * pointer would say the app was busy rather than that you are already
   * there.
   */
  private chooser() {
    return html`
      <div class="views" role="group" aria-label="views">
        ${VIEWS.map((view) => {
          const current = view.id === this.view;
          return html`
            <button
              class=${`view ${current ? "current" : ""}`}
              data-view=${view.id}
              title=${view.label}
              aria-label=${view.label}
              aria-pressed=${current}
              @click=${() =>
                this.dispatchEvent(
                  new CustomEvent<ViewId>("view-wanted", {
                    detail: view.id,
                    bubbles: true,
                    composed: true,
                  }),
                )}
            >
              ${ICONS[view.id]}
            </button>
          `;
        })}
      </div>
    `;
  }

  /**
   * Which railroad is loaded, and the way to another (#167). It is the band's
   * because it is the whole system's: both views are of it, and a menu on one
   * view's bar would be the editor deciding what the run view is looking at.
   *
   * **It asks and does not load.** One broker runs one railroad and the layout
   * interface says which on a retained row
   * ([ADR-0059](../../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
   * decision 2), and which one that is is a person's choice made **while the
   * apps run**
   * ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
   * So choosing one publishes `railroad_wanted` and stops there; the name
   * above goes on being the row the layout interface answered with, and a
   * gesture nothing answered leaves it alone.
   *
   * The railroad that is loaded is ticked, and the tick is all that entry is:
   * choosing it asks for nothing (#101), because the app would throw away
   * whatever has been drawn since when the row came back — a lot to ask of a
   * click that looks like it does nothing.
   *
   * **Track power off is the precondition.** While the rails have power the
   * picker is dead and says why: a train already under a committed route keeps
   * rolling whatever the software forgets, and with the power off nothing
   * moves and no turnout throws. Nothing here turns it off — that is the
   * panel's OFF, which drains the run first and is already a gesture a person
   * has (ADR-0051, ADR-0060). Power reads `null` with no session joined, which
   * is a page with nothing to ask at all, so the one condition covers both.
   */
  private picker() {
    const name = this.drawing ?? "no railroad";
    const why = this.reason;
    return html`
      ${this.picking ? dismissal(() => this.pick(false)) : nothing}
      <div class="picker">
        <button
          class="chosen"
          aria-haspopup="true"
          aria-expanded=${this.picking}
          title=${why ?? "load another railroad"}
          ?disabled=${why !== null}
          @click=${() => this.pick(!this.picking)}
        >
          <span class="drawing">${name}</span>
          <span class="more">▾</span>
        </button>
        ${this.picking
          ? html`
              <menu class="drawings">
                ${this.drawings.map(
                  (one) => html`
                    <li>
                      <button @click=${() => this.wanting(one)}>
                        <span class="tick">${one === this.drawing ? "✓" : ""}</span>
                        <span class="label">${one}</span>
                      </button>
                    </li>
                  `,
                )}
              </menu>
            `
          : nothing}
      </div>
    `;
  }

  /** Why the picker is dead, `null` while it is live. The words are what the
   *  button says when it is hovered, because a control that is dead and
   *  silent reads as an app that is broken. */
  private get reason(): string | null {
    if (this.power === null) return "no railroad is running to ask";
    if (this.power !== "off") {
      return "the track has power: switch it off to load another railroad";
    }
    if (this.drawings.length === 0) return "the store lists no railroad";
    return null;
  }

  /** Put the list down, or take it up. The app is told either way: the band
   *  sits above the bar, so a press here lands on the picker rather than on
   *  the overlay a menu on the bar is waiting for, and the menu would be left
   *  down with the keyboard still its. */
  private pick(down: boolean): void {
    if (this.picking === down) return;
    this.picking = down;
    this.dispatchEvent(
      new CustomEvent<boolean>("picker-open", {
        detail: down,
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** One of the railroads was chosen. The band says which is wanted and stops
   *  there — the bus is what loads it, and the app is what carries the press
   *  (ADR-0060). */
  private wanting(name: string): void {
    this.pick(false);
    if (name === this.drawing) return;
    this.dispatchEvent(
      new CustomEvent<string>("railroad-wanted", {
        detail: name,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

/** Elapsed seconds as a clock: `mm:ss`, hours in front once there are any. */
function clocked(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const s = String(seconds % 60).padStart(2, "0");
  return h > 0 ? `${h}:${m}:${s}` : `${m}:${s}`;
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-header": TcHeader;
  }
}
