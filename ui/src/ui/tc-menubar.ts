/**
 * The bar under the band: `File`, `Edit` and `View`, and the three buttons
 * pressed too often to be in a menu.
 *
 * Every verb the editor has lives in a menu here, with its key printed beside
 * it. That is what EDITOR.md#editing asks for — the header carries no bare
 * verb button, and a shortcut is learnt where it is conventionally read — and
 * it is why the drawing select, New…, Save As… and Save are no longer buttons
 * on the page.
 *
 * Zoom out, zoom in and fit stay one click at the right end. They are pressed
 * constantly while drawing and `View ▸ Zoom in` is three clicks for what is
 * now one.
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
import { GLYPHS } from "./icons.js";
import { menubarStyles } from "./tc-menubar.styles.js";

@customElement("tc-menubar")
export class TcMenubar extends LitElement {
  static override styles = menubarStyles;

  /** What the editor has, as far as an item needs to know to be alive. */
  @property({ attribute: false }) standing: Standing = NOTHING;

  /** The drawings `Open` lists. */
  @property({ attribute: false }) drawings: string[] = [];

  /** The menu that is down, `null` while none is. */
  @state() private showing: string | null = null;

  /** Whether `Open`'s drawings are showing beside the `File` menu. */
  @state() private listing = false;

  override render() {
    return html`
      ${this.showing === null
        ? nothing
        : html`<div class="sheet" @pointerdown=${() => this.show(null)}></div>`}
      ${MENUS.map((menu) => this.dropdown(menu))}
      <span class="spacer"></span>
      ${TOOLS.map((id) => this.tool(id))}
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
          @click=${() => this.show(down ? null : menu.name)}
          @pointerenter=${() => {
            // Once a menu is down, sliding along the bar reads the next one,
            // which is what every menu bar does.
            if (this.showing !== null) this.show(menu.name);
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
    if (id === "open") return this.opener();
    const command = COMMANDS[id];
    const alive = command.enabled(this.standing);
    return html`
      <li @pointerenter=${() => (this.listing = false)}>
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

  /** `Open` is a submenu rather than a dialog: layouts are edited rarely
   *  (EDITOR.md), so the list is short and stays short. The drawing that is
   *  open is ticked. */
  private opener() {
    const command = COMMANDS["open"];
    const alive = command.enabled(this.standing);
    return html`
      <li
        class="submenu"
        @pointerenter=${() => (this.listing = alive)}
      >
        <button ?disabled=${!alive} @click=${() => (this.listing = alive)}>
          <span class="glyph">${GLYPHS["open"]}</span>
          <span class="label">${command.label}</span>
          <span class="more">▸</span>
        </button>
        ${this.listing
          ? html`
              <menu class="drawings">
                ${this.drawings.map(
                  (name) => html`
                    <li>
                      <button @click=${() => this.opening(name)}>
                        <span class="tick"
                          >${name === this.standing.opened ? "✓" : ""}</span
                        >
                        <span class="label">${name}</span>
                      </button>
                    </li>
                  `,
                )}
              </menu>
            `
          : nothing}
      </li>
    `;
  }

  /** One of the three the bar pins at its right end. The glyph is the whole
   *  of it, so the label and its key are what a pointer resting there says. */
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

  private opening(name: string): void {
    this.show(null);
    this.dispatchEvent(
      new CustomEvent<string>("open-drawing", {
        detail: name,
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Put a menu down, or take them all up. The editor is told either way: with
   *  a menu down the keyboard is the menu's, and `r` reaching the canvas from
   *  under an open `File` would rotate the selection behind it. */
  private show(name: string | null): void {
    if (this.showing === name) return;
    this.showing = name;
    this.listing = false;
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
