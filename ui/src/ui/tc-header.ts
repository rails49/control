/**
 * The band across the top: what is true of the whole system
 * ([ADR-0038](../../../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
 *
 * Which railroad is loaded and the way to another, whether it holds unsaved
 * edits, and whether what the app talks to is answering. The rail down the
 * left carries what acts on the current view's document, the selector that
 * switches view among it
 * ([ADR-0064](../../../docs/adr/0064-the-chrome-is-a-band-and-a-rail.md)).
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
import { dismissal } from "./dismissal.js";
import { headerStyles } from "./tc-header.styles.js";

/** What each power value reads as, which is what the press standing at it says
 *  when it is hovered. `stopped` reads as the thing rather than as the token,
 *  because the two ask for different actions: an emergency stop is cleared,
 *  and a supply that is off is switched back on. */
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

  /** Whether a session is joined, which is what makes the broker a thing to
   *  report on at all. */
  @property({ type: Boolean }) joined = false;

  /** What the app could not do — the store not answering, a broker that is
   *  not there, a name no drawing can wear. Never a fault of the drawing
   *  itself: those are marked where they are (ADR-0024). */
  @property() trouble: string | null = null;

  /** What the hardware says is wrong with the supply, in its own words,
   *  `null` where it says nothing (BUS.md, device vocabulary). The run view
   *  reads it off `tc49/layout/state/device/track`, whose free-text `reason`
   *  is the only place a tripped district can be said — a district reaches no
   *  topic of its own
   *  ([ADR-0050](../../../docs/adr/0050-broken-hardware-is-reported-never-worked-around.md),
   *  [#602](https://github.com/rails49/control/issues/602)).
   *
   *  Not the supply's reading, which is the mark on the presses and cannot
   *  carry this: a station that cuts one district by itself goes on reporting
   *  the railroad as powered, and a marked OFF wears the plain mark since
   *  #585, so a dark railroad reads as one at rest. So it reads whichever way
   *  `power` stands, and it is the hardware's sentence verbatim — nothing
   *  here branches on it. */
  @property() fault: string | null = null;

  /** Whether the drawing derives, which is the one thing the band says about
   *  the drawing itself (ADR-0024). The mark names no fault and counts
   *  nothing: the canvas is where you find out where. */
  @property({ type: Boolean }) derives = true;

  /** Whether to say the drawing is frozen: a train is on the layout, so the
   *  editing view is read-only until it is off it (`model/commands.ts`,
   *  ADR-0038).
   *
   *  **Whether, and not merely that.** The app hands this over in the editing
   *  view alone (#517). The mark exists to explain the dead verbs, and they are
   *  the editor's; trains on the layout are the ordinary state of a railroad
   *  being run, so in the run view the same mark is a warning about nothing.
   *  The band decides no such thing itself — which view is current is the app's
   *  and left the band with the selector (ADR-0064). */
  @property({ type: Boolean }) frozen = false;

  /** What backup has to say without being asked, and why — `null` where it
   *  says nothing (`model/backup.ts`, #688). The same rule the mark on
   *  `File ▸ Backup…` follows, read here so that a person running trains, with
   *  the editing view shut, learns of a backup that is not running. */
  @property({ attribute: false }) backup: { says: string; why: string } | null = null;

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
      ${this.health()} ${this.supply()}
    `;
  }

  /**
   * What the app could not do, and how far the run has got.
   *
   * **Nothing that is going right reads here** (#517). The band was a row of
   * six entries with five of them saying the ordinary thing — `drawing frozen
   * connected power on session 12:04` — and a status line that is always full
   * is one nobody reads, so the entry that matters is not seen either. So each
   * of them speaks only where a person would act on it:
   *
   * - **The link** has no word of its own at all. Connected is the ordinary
   *   case; not connected is `trouble`, in a sentence that names the broker
   *   and asks whether the bus is running (`tc-panel.ts`).
   * - **Track power** is the mark on the press that names where it stands, not
   *   a reading beside them ([Supply](#supply)). Three buttons plus a word
   *   repeating one of them was the same fact twice.
   * - **The frozen drawing** reads in the editing view alone, that being where
   *   the dead verbs it explains are. Trains on the layout are the ordinary
   *   state of a railroad being run, and nothing is wrong with it, so in the
   *   run view it is a warning about nothing.
   *
   * - **A fault the hardware reports** speaks wherever it is standing, and the
   *   mark on the presses cannot say it: a station that cuts one district by
   *   itself goes on reporting the railroad as powered, and a district reaches
   *   no topic of its own, so the row's free-text `reason` is the whole of
   *   what says a trip is standing (ADR-0050, #602). It is the railroad's own
   *   and the trouble above is the app's, so the two stand beside each other
   *   rather than one standing in for the other.
   *
   * - **Backup that is not running** says so in words naming what is wrong,
   *   and is a press that opens `File ▸ Backup…` (#688). The copy off the box
   *   stopped for five weeks once with the only sign a mark in the editing
   *   view, which is not open while trains run.
   *
   * What is left is the four things that are somebody's mistake — the store
   * not answering or a broker that is not, a drawing that does not derive,
   * hardware saying what is wrong with the supply, and a backup that is not
   * running — and the session clock.
   *
   * A region rather than a string, with room in it: per-container reachability
   * and eventually the hardware's belong here too, and what fills the slot is
   * the deployment design's (`2a-docker`).
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
        ${this.fault === null
          ? nothing
          : html`<span class="fault" title=${this.fault}>${this.fault}</span>`}
        ${this.backup === null
          ? nothing
          : html`<button
              class="backup"
              title=${this.backup.why}
              @click=${() =>
                this.dispatchEvent(
                  new CustomEvent<void>("backup-wanted", {
                    bubbles: true,
                    composed: true,
                  }),
                )}
            >
              ${this.backup.says}
            </button>`}
        ${this.sessionS === null
          ? nothing
          : html`<span class="session">session ${clocked(this.sessionS)}</span>`}
      </div>
    `;
  }

  /**
   * ON, STOP and OFF: what the whole railroad's supply should be doing
   * (ADR-0051). They stand beside the reading rather than on the rail, which
   * is the current view's document's — track power is no document's.
   *
   * **The press that names where the supply stands is marked** (#517). It is
   * the same mark the rail puts on the current view: the list is what the
   * supply can be doing and the current one is one of them, so the three
   * buttons are the reading as well as the presses and the band needs no word
   * beside them. STOP wears the alarm while it is the one marked, an emergency
   * stop being somebody's to clear and not a state to leave a railroad in. ON
   * and OFF marked wear the plain mark: red on the chrome is a stop or a fault
   * and nothing else, and a supply switched off is neither — it is where the
   * railroad rests and comes up (ADR-0054, #585).
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
          const at = power === this.power;
          return html`
            <button
              class=${`press ${power}${at ? " at" : ""}${waiting ? " waiting" : ""}`}
              aria-pressed=${at}
              title=${waiting
                ? "waiting for the run to drain"
                : at
                  ? POWERED[this.power!]
                  : says}
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
   * Which railroad is loaded, and the way to another (#167). It is the band's
   * because it is the whole system's: both views are of it, and a menu on one
   * view's rail would be the editor deciding what the run view is looking at.
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

  /** Put the list down, or take it up. The app is told either way: the picker
   *  is the one thing on the band that hangs over anything, so what it is doing
   *  is the band's own to report. */
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
