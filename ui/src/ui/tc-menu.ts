/**
 * The right-click menu: what applies to whatever was clicked.
 *
 * A junction region offers its name, because renaming one is meant to be one
 * click on the region; a bare wire between two blocks offers the name of the
 * connection it is; a symbol offers its properties and the transforms the key
 * bindings also do; and a wire offers to be cut, this being the only way to
 * delete one — a wire has no symbol to select and so no keystroke to take it.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { Under } from "../model/under.js";
import { menuStyles } from "./styles.js";

export type MenuAction =
  | "properties"
  | "rename-junction"
  | "rename-joint"
  | "rotate"
  | "flip"
  | "delete"
  | "delete-wire";

/** Where the pointer was, and what was under it. The canvas works out the
 *  second half (model/under.ts) and the menu only asks what applies to it. */
export type MenuAt = Under & { x: number; y: number };

@customElement("tc-menu")
export class TcMenu extends LitElement {
  static override styles = menuStyles;

  @property({ attribute: false }) at: MenuAt | null = null;

  override render() {
    const at = this.at;
    // Nothing under the pointer applies to nothing, and a menu of no items is
    // an empty box that looks broken. A wire is the ordinary way to land here:
    // it is not a symbol, and only the bare wire between two blocks is a joint
    // with a name to offer.
    if (at === null || !applies(at)) return nothing;
    return html`
      <div class="sheet" @pointerdown=${this.dismiss}></div>
      <menu style=${`left: ${at.x}px; top: ${at.y}px`}>
        ${at.junction === null
          ? nothing
          : this.item(
              "rename-junction",
              `Rename junction "${at.junction.name ?? "unnamed"}"`,
            )}
        ${at.joint === null
          ? nothing
          : this.item(
              "rename-joint",
              `Rename connection "${at.joint.name ?? "unnamed"}"`,
            )}
        ${at.wire === null ? nothing : this.item("delete-wire", "Delete wire")}
        ${at.symbol === null
          ? nothing
          : html`
              ${this.item("properties", "Properties…")}
              ${this.item("rotate", "Rotate", "R")}
              ${this.item("flip", "Flip", "F")}
              ${this.item("delete", "Delete", "⌫")}
            `}
      </menu>
    `;
  }

  /** The key goes beside the item that does the same thing. With the transforms
   *  off the header this is where they are learnt, a menu being where a
   *  shortcut is conventionally read (EDITOR.md#editing). */
  private item(action: MenuAction, label: string, key?: string) {
    return html`
      <li>
        <button @click=${() => this.choose(action)}>
          <span>${label}</span>
          ${key === undefined ? nothing : html`<kbd>${key}</kbd>`}
        </button>
      </li>
    `;
  }

  private choose(action: MenuAction): void {
    this.dispatchEvent(
      new CustomEvent<MenuAction>("menu-action", {
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

/** Whether anything was clicked that the menu has something to say about. */
export function applies(at: MenuAt): boolean {
  return (
    at.symbol !== null ||
    at.junction !== null ||
    at.joint !== null ||
    at.wire !== null
  );
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-menu": TcMenu;
  }
}
