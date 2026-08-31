/**
 * The bar under the band: the menus of the view that is current, and the
 * buttons pressed too often to be in one.
 *
 * The bar is the document's (ADR-0038): it acts on what the current view has
 * open, and which view that is decides which menus it carries. The band above
 * carries what is true of the whole system, the loaded railroad included, so
 * no menu here opens one.
 *
 * Every verb a view has lives in a menu, with its key printed beside it. That
 * is what EDITOR.md#editing asks for — the band carries no bare verb button,
 * and a shortcut is learnt where it is conventionally read — and it is why
 * New…, Save As… and Save are no longer buttons on the page.
 *
 * Zoom out, zoom in and fit stay one click at the right end of the editor's
 * bar. They are pressed constantly while drawing and `View ▸ Zoom in` is three
 * clicks for what is now one.
 *
 * What is dead and what is alive is `model/commands.ts`, tested with no DOM.
 * This component draws what that module says and dispatches an id; it decides
 * nothing.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import {
  COMMANDS,
  MENUS,
  NOTHING,
  TOOLS,
  type CommandId,
  type Menu,
  type Standing,
} from "../model/commands.js";
import type { Power, Run } from "../model/trace.js";
import type { ViewId } from "../model/views.js";
import { dismissal } from "./dismissal.js";
import { GLYPHS } from "./icons.js";
import { menubarStyles } from "./tc-menubar.styles.js";

@customElement("tc-menubar")
export class TcMenubar extends LitElement {
  static override styles = menubarStyles;

  /** The view whose menus the bar is carrying. */
  @property() view: ViewId = "edit";

  /** Where that view stands, as far as an item needs to know to be alive. */
  @property({ attribute: false }) standing: Standing = NOTHING;

  /** How the run stands, `null` with no session joined. The run view's own
   *  press, and the one thing on this bar that is not a command: it has no
   *  key, its word is the run's rather than a verb's, and what it writes is a
   *  gesture on the bus (ADR-0037). */
  @property() run: Run | null = null;

  /** Whether the layout says a train may move at all, `null` with no session
   *  joined and before it has said (ADR-0041). GO is greyed while it is
   *  anything but `on`; the band is where the word itself reads. */
  @property() power: Power | null = null;

  /** The menu that is down, `null` while none is. */
  @state() private showing: string | null = null;

  /** Whether the menu that is down was opened by the pointer sliding onto its
   *  title rather than by a click on it, and the click the hand is about to
   *  land there has yet to be absorbed. */
  private hovered = false;

  override willUpdate(changed: Map<string, unknown>): void {
    // A menu is the view's, so it goes up with the view. One left down would
    // be drawing the titles of a view that is no longer on screen.
    if (changed.has("view")) this.showing = null;
  }

  override render() {
    return html`
      ${this.showing === null
        ? nothing
        : dismissal(() => this.show(null))}
      ${MENUS[this.view].map((menu) => this.dropdown(menu))}
      <span class="spacer"></span>
      ${TOOLS[this.view].map((id) => this.tool(id))}
      ${this.view === "run" ? this.holding() : nothing}
    `;
  }

  /** Close whatever is down. The editor calls this on Escape, which it takes
   *  before the canvas does while a menu is open. */
  close(): void {
    this.show(null);
  }

  private dropdown(menu: Menu) {
    const down = this.showing === menu.name;
    return html`
      <div class="menu">
        <button
          class=${`title ${down ? "on" : ""}`}
          aria-haspopup="true"
          aria-expanded=${down}
          @click=${() => this.pressed(menu.name)}
          @pointerenter=${() => {
            // Once a menu is down, sliding along the bar reads the next one,
            // which is what every menu bar does.
            if (this.showing !== null) this.show(menu.name, true);
          }}
        >
          ${menu.name}
        </button>
        ${down
          ? html`<menu>${menu.items.map((item) => this.item(item))}</menu>`
          : nothing}
      </div>
    `;
  }

  private item(id: CommandId | null) {
    if (id === null) return html`<li class="divider" role="separator"></li>`;
    const command = COMMANDS[id];
    const alive = command.enabled(this.standing);
    return html`
      <li>
        <button ?disabled=${!alive} @click=${() => this.choose(id)}>
          <span class="glyph">${GLYPHS[id]}</span>
          <span class="label">${command.label}</span>
          ${command.key === undefined
            ? nothing
            : html`<kbd>${command.key}</kbd>`}
        </button>
      </li>
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
   * beside it says `power off` or `emergency stop`, which is the reason, the
   * way the panel's greyed "Turn around" says *this train is busy* by being
   * greyed at all. HOLD is never greyed: it asks for less, and there is no
   * state of the rails in which a person may not ask for it.
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

  /** One of the ones the bar pins at its right end. The glyph is the whole of
   *  it, so the label and its key are what a pointer resting there says. */
  private tool(id: CommandId) {
    const command = COMMANDS[id];
    const said = `${command.label}  ${command.key ?? ""}`.trim();
    return html`
      <button
        class="tool"
        title=${said}
        aria-label=${said}
        @click=${() => this.choose(id)}
      >
        ${GLYPHS[id]}
      </button>
    `;
  }

  /** A click on a title. It opens the menu, or takes it up when that menu is
   *  already down — except for the click that lands on a title the hand has
   *  just hovered onto, which is the hover's own and is absorbed (#100).
   *  Closing there would undo the menu the same gesture just asked for. */
  private pressed(name: string): void {
    if (this.showing !== name) {
      this.show(name);
    } else if (this.hovered) {
      this.hovered = false;
    } else {
      this.show(null);
    }
  }

  private choose(id: CommandId): void {
    this.show(null);
    this.dispatchEvent(
      new CustomEvent<CommandId>("command", {
        detail: id,
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Put a menu down, or take them all up. The editor is told either way: with
   *  a menu down the keyboard is the menu's, and `r` reaching the canvas from
   *  under an open `File` would rotate the selection behind it. `hovered` says
   *  the pointer put it down rather than a click, which is what `pressed`
   *  reads to absorb the click that follows. */
  private show(name: string | null, hovered = false): void {
    if (this.showing === name) return;
    this.showing = name;
    this.hovered = hovered;
    this.dispatchEvent(
      new CustomEvent<boolean>("menu-open", {
        detail: name !== null,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-menubar": TcMenubar;
  }
}
