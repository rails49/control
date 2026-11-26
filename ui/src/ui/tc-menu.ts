/**
 * A right-click menu: the items it is given, at the point it is given. The
 * timetable's heading hangs one under a button (`tc-timetable-controls`).
 *
 * Items are data — a label, the action choosing one sends, an optional key
 * printed beside it, whether it is greyed, and optionally why. What applies
 * to whatever was clicked is the page's question and not the menu's: the editor works out
 * what a symbol or a wire offers, the panel what a train does. What is shared
 * is the fiddly half — dismissal on a press outside, positioning at the
 * pointer, and the keycap column.
 *
 * No items is no menu: an empty rounded box on the canvas looks broken.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/tooltip/tooltip.js";

import { dismissal } from "./dismissal.js";
import { menuStyles } from "./tc-menu.styles.js";

/** One row: what it says, what choosing it sends, the key that does the same
 *  thing, and whether it can be chosen at all. A disabled row says *this does
 *  not apply just now*, where leaving it out says nothing. */
export interface MenuItem {
  label: string;
  action: string;
  key?: string;
  disabled?: boolean;
  /** Why a disabled row cannot be chosen. It is the row's tooltip and its
   *  description, as the rail's is for a view that does not open. */
  reason?: string;
}

@customElement("tc-menu")
export class TcMenu extends LitElement {
  static override styles = menuStyles;

  /** Where the pointer was, in page pixels; `null` for no menu at all. */
  @property({ attribute: false }) at: { x: number; y: number } | null = null;
  @property({ attribute: false }) items: readonly MenuItem[] = [];

  override render() {
    const at = this.at;
    if (at === null || this.items.length === 0) return nothing;
    return html`
      ${dismissal(() => this.dismiss())}
      <menu style=${`left: ${at.x}px; top: ${at.y}px`}>
        ${this.items.map((item) => this.row(item))}
      </menu>
    `;
  }

  /** The key goes beside the item that does the same thing. With the editor's
   *  transforms off the header this is where they are learnt, a menu being
   *  where a shortcut is conventionally read (EDITOR.md#editing). */
  private row(item: MenuItem) {
    const why = item.disabled ? (item.reason ?? "") : "";
    if (why !== "") {
      // Not `disabled`: a disabled button takes no focus and no hover, so its
      // tooltip would never open.
      return html`
        <li>
          <sl-tooltip content=${why} hoist>
            <button aria-disabled="true" aria-description=${why}>
              <span>${item.label}</span>
            </button>
          </sl-tooltip>
        </li>
      `;
    }
    return html`
      <li>
        <button
          ?disabled=${item.disabled ?? false}
          @click=${() => this.choose(item.action)}
        >
          <span>${item.label}</span>
          ${item.key === undefined ? nothing : html`<kbd>${item.key}</kbd>`}
        </button>
      </li>
    `;
  }

  private choose(action: string): void {
    this.dispatchEvent(
      new CustomEvent<string>("menu-action", {
        detail: action,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private dismiss(): void {
    this.dispatchEvent(
      new CustomEvent("menu-dismissed", { bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-menu": TcMenu;
  }
}
