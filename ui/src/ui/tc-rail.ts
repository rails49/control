/**
 * The rail down the left: the views, the current view's commands, and any
 * press of its own
 * ([ADR-0064](../../../docs/adr/0064-the-chrome-is-a-band-and-a-rail.md)).
 *
 * The rail is where a person presses things. The band above carries what is
 * true of the whole system, the loaded railroad included, so nothing here
 * loads one; what is here acts on the document the current view has open
 * (ADR-0038), which is what decides the groups it carries.
 *
 * Every verb a view has is a button, with its label and its key in the title,
 * which is what a menu row printed beside it. That is what EDITOR.md#editing
 * asks for — the band carries no bare verb button, and a shortcut is read
 * where the verb is — one row of chrome later.
 *
 * What is dead and what is alive is `model/commands.ts`, tested with no DOM.
 * This component draws what that module says and dispatches an id; it decides
 * nothing.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import {
  COMMANDS,
  NOTHING,
  RAIL,
  type CommandId,
  type Group,
  type Standing,
} from "../model/commands.js";
import type { Power, Run } from "../model/trace.js";
import { VIEWS, type ViewId } from "../model/views.js";
import { GLYPHS, ICONS } from "./icons.js";
import { railStyles } from "./tc-rail.styles.js";

@customElement("tc-rail")
export class TcRail extends LitElement {
  static override styles = railStyles;

  /** The view that is current: the one the top group marks, and the one whose
   *  groups the rest of the rail carries. */
  @property() view: ViewId = VIEWS[0]!.id;

  /** Where that view stands, as far as a button needs to know to be alive. */
  @property({ attribute: false }) standing: Standing = NOTHING;

  /** How the run stands, `null` with no session joined. The run view's own
   *  press, and the one thing on the rail that is not a command: it has no
   *  key, its word is the run's rather than a verb's, and what it writes is a
   *  gesture on the bus (ADR-0037). */
  @property() run: Run | null = null;

  /** Whether the layout says a train may move at all, `null` with no session
   *  joined and before it has said (ADR-0041). GO is greyed while it is
   *  anything but `on`; the band is where the word itself reads. */
  @property() power: Power | null = null;

  override render() {
    return html`
      ${this.chooser()}
      ${RAIL[this.view].map((group) => this.group(group))}
      ${this.view === "run" ? this.holding() : nothing}
    `;
  }

  /**
   * Which view is current, and the way to each of the others: **a selector**,
   * one icon-button per view with the current one marked.
   *
   * The views are a list with one current entry (`model/views.ts`), and
   * ADR-0038 wrote down what the list is for: a fourth entry is a button
   * added rather than a redesign. It is the rail's top group rather than the
   * band's right end (ADR-0064) — the rail is where a person presses things,
   * and on the band it competed for the same end of the row as track power.
   *
   * The current view's own button is live and asks for the view it is
   * already showing. Nothing happens — the app ignores a switch to the view
   * it holds — and a control whose only dead button is the one under the
   * pointer would say the app was busy rather than that you are already
   * there.
   */
  private chooser() {
    return html`
      <div class="group" role="group" aria-label="views">
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

  /** One run of the current view's commands. The group is what says which of
   *  them belong together, the menu titles having gone with the bar, so the
   *  name it was drawn under is the group's accessible name (ADR-0064). */
  private group(group: Group) {
    return html`
      <div class="group" role="group" aria-label=${group.name}>
        ${group.items.map((id) => this.button(id))}
      </div>
    `;
  }

  /** One command. The glyph is the whole of it, so the label and its key are
   *  what a pointer resting there says — what the menu row printed. */
  private button(id: CommandId) {
    const command = COMMANDS[id];
    const alive = command.enabled(this.standing);
    // What the button has to say before it is pressed, which is backup's alone
    // (#321). It warns and never disables: a railroad that is not being backed
    // up is a railroad somebody still has to be able to back up.
    const says = command.mark?.(this.standing) ?? null;
    const said = `${command.label}  ${command.key ?? ""}`.trim();
    return html`
      <button
        data-command=${id}
        title=${says ?? said}
        aria-label=${said}
        ?disabled=${!alive}
        @click=${() =>
          this.dispatchEvent(
            new CustomEvent<CommandId>("command", {
              detail: id,
              bubbles: true,
              composed: true,
            }),
          )}
      >
        ${GLYPHS[id]}
        ${says === null ? nothing : html`<span class="mark" aria-label=${says}>!</span>`}
      </button>
    `;
  }

  /**
   * HOLD while the run is running and GO while it is held: one press, and the
   * word is what the press will do (ADR-0037). No confirmation — a clearly
   * labelled button is the explicit GO, and asking twice for the same answer
   * is how a person learns to click through the question.
   *
   * Dead with no session joined, there being no run to hold, and dead until
   * the dispatcher has said where the run stands: a button guessing would
   * offer to hold a run that is already held.
   *
   * **GO is greyed while the rails are dead**, because the dispatcher drops
   * such a release: letting it through would grant moves and publish `move`
   * over track nothing can move on, and strand the next train (ADR-0041).
   * Greyed and not hidden, and with no explanation of its own — the band
   * says `power off` or `emergency stop`, which is the reason, the way the
   * panel's greyed "Turn around" says *this train is busy* by being greyed at
   * all.  HOLD is never greyed: it asks for less, and there is no state of the
   * rails in which a person may not ask for it.
   */
  private holding() {
    const going = this.run === "running";
    const said = going ? "HOLD" : "GO";
    const dead = !going && this.power !== null && this.power !== "on";
    return html`
      <button
        class=${`run ${going ? "hold" : "go"}`}
        ?disabled=${this.run === null || dead}
        @click=${() =>
          this.dispatchEvent(
            new CustomEvent<Run>("run-wanted", {
              detail: going ? "held" : "running",
              bubbles: true,
              composed: true,
            }),
          )}
      >
        ${said}
      </button>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-rail": TcRail;
  }
}
