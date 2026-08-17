/**
 * The right-click menu: what applies to whatever was clicked.
 *
 * A junction region offers its name, because renaming one is meant to be one
 * click on the region; a bare wire between two blocks offers the name of the
 * connection it is; a symbol offers its properties and the transforms the key
 * bindings also do.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { Joint, Junction } from "../model/store.js";
import { menuStyles } from "./styles.js";

export type MenuAction =
  | "properties"
  | "rename-junction"
  | "rename-joint"
  | "rotate"
  | "flip"
  | "delete";

export interface MenuAt {
  x: number;
  y: number;
  symbol: string | null;
  junction: Junction | null;
  joint: Joint | null;
}

@customElement("tc-menu")
export class TcMenu extends LitElement {
  static override styles = menuStyles;

  @property({ attribute: false }) at: MenuAt | null = null;

  override render() {
    const at = this.at;
    if (at === null) return nothing;
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
        ${at.symbol === null
          ? nothing
          : html`
              ${this.item("properties", "Properties…")}
              ${this.item("rotate", "Rotate")} ${this.item("flip", "Flip")}
              ${this.item("delete", "Delete")}
            `}
      </menu>
    `;
  }

  private item(action: MenuAction, label: string) {
    return html`
      <li>
        <button @click=${() => this.choose(action)}>${label}</button>
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

declare global {
  interface HTMLElementTagNameMap {
    "tc-menu": TcMenu;
  }
}
