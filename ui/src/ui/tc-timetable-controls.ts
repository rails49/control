/**
 * The controls in the heading of the list under the roster
 * ([#1345](https://github.com/rails49/control/issues/1345),
 * [#1357](https://github.com/rails49/control/issues/1357)): a menu with New,
 * Load, Rename, Delete and Repeat
 * ([#1368](https://github.com/rails49/control/issues/1368)), the Record
 * switch, and Start while the loaded timetable's phase is `loaded`.
 *
 * The run view puts it in `tc-requests`'s heading and hands it the timetable
 * the scheduler says is loaded, the railroad and the track power.
 *
 * - **The menu** is `tc-menu`, hung under its button. Each row opens a
 *   dialog (`tc-timetable-dialog`). Rename and Repeat are disabled with no
 *   timetable loaded. New, Load and Repeat are disabled while track power is
 *   on, and say so as the rail does for a view that does not open: the
 *   scheduler takes them only with power `off`.
 * - **Record** shows the row's `record`, not the last press. It is disabled
 *   with no timetable loaded.
 * - **Start** is drawn only while the phase is `loaded`.
 *
 * It changes nothing by itself. A press raises `timetable-wanted` with the
 * frame the gesture is (`model/trace.ts`), the run view hands that to the
 * session, and what is drawn afterwards is what `state/timetable` then says.
 *
 * @fires timetable-wanted - `CustomEvent<Frame>`: the gesture to publish.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { powered, type Timetable } from "../model/timetable.js";
import {
  timetableRecordWanted,
  timetableStartWanted,
  type Frame,
  type Power,
} from "../model/trace.js";
import "./tc-menu.js";
import type { MenuItem } from "./tc-menu.js";
import { timetableControlsStyles } from "./tc-timetable-controls.styles.js";
import "./tc-timetable-dialog.js";
import type { Asked } from "./tc-timetable-dialog.js";

@customElement("tc-timetable-controls")
export class TcTimetableControls extends LitElement {
  static override styles = timetableControlsStyles;

  /** The loaded timetable, `null` for none. */
  @property({ attribute: false }) timetable: Timetable | null = null;

  /** The railroad the session is joined to, whose timetables the store has. */
  @property({ attribute: false }) railroad = "";

  /** Track power as the layout last said it, `null` before it has. */
  @property({ attribute: false }) power: Power | null = null;

  /** Whether a session is joined: there is a scheduler to ask and a railroad
   *  to name to the store. */
  @property({ type: Boolean }) live = false;

  /** Where the open menu hangs, in page pixels, `null` while it is shut. */
  @state() private menu: { x: number; y: number } | null = null;

  /** The row whose dialog is open, `null` for none. */
  @state() private asked: Asked | null = null;

  override render() {
    const timetable = this.timetable;
    const record = timetable?.record ?? false;
    return html`
      <button
        class="menu"
        aria-label="Timetable menu"
        aria-haspopup="menu"
        ?disabled=${!this.live}
        @click=${this.open}
      >
        ⋯
      </button>
      <button
        class="record"
        role="switch"
        aria-checked=${record ? "true" : "false"}
        ?disabled=${timetable === null}
        @click=${() => this.wanted(timetableRecordWanted(!record))}
      >
        <i></i>Record
      </button>
      ${timetable?.phase === "loaded"
        ? html`<button class="start" @click=${() => this.wanted(timetableStartWanted())}>
            Start
          </button>`
        : nothing}
      <tc-menu
        .at=${this.menu}
        .items=${this.items}
        @menu-action=${this.chose}
        @menu-dismissed=${() => {
          this.menu = null;
        }}
      ></tc-menu>
      ${this.asked === null
        ? nothing
        : html`<tc-timetable-dialog
            .asked=${this.asked}
            .timetable=${timetable}
            .railroad=${this.railroad}
            .power=${this.power}
            @timetable-dialog-closed=${() => {
              this.asked = null;
            }}
          ></tc-timetable-dialog>`}
    `;
  }

  /** The menu's rows. Each row's action is the dialog it opens. */
  private get items(): MenuItem[] {
    const shut = powered(this.power);
    const rows: [string, Asked, boolean, string?][] = [
      ["New", "new", shut !== "", shut],
      ["Load", "load", shut !== "", shut],
      ["Rename", "rename", this.timetable === null],
      ["Delete", "delete", false],
      ["Repeat", "repeat", this.timetable === null || shut !== "", shut],
    ];
    return rows.map(([label, action, disabled, reason]) => ({
      label,
      action,
      disabled,
      ...(reason ? { reason } : {}),
    }));
  }

  /** The menu hangs from the bottom left corner of its button. */
  private open = (event: Event): void => {
    const box = (event.currentTarget as Element).getBoundingClientRect();
    this.menu = { x: box.left, y: box.bottom };
  };

  private chose = (event: CustomEvent<string>): void => {
    this.menu = null;
    this.asked = event.detail as Asked;
  };

  private wanted(frame: Frame): void {
    this.dispatchEvent(
      new CustomEvent<Frame>("timetable-wanted", {
        detail: frame,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-timetable-controls": TcTimetableControls;
  }
}
