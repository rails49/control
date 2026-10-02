/**
 * PROTOTYPE — throwaway, never merged to main (#628).
 *
 * The bar that flips between the photo variants (`?variant=`), with ← and →
 * as keys, and a switch that makes the stub camera fail.
 */

import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";

import { VARIANTS, variant } from "./photo.js";

@customElement("proto-switcher")
export class ProtoSwitcher extends LitElement {
  static override styles = css`
    :host {
      position: fixed;
      bottom: 1rem;
      left: 50%;
      transform: translateX(-50%);
      z-index: 10000;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.35rem 0.8rem;
      border-radius: 999px;
      background: #111;
      color: #fff;
      font: 0.8rem system-ui, sans-serif;
      box-shadow: 0 4px 16px rgb(0 0 0 / 0.35);
    }
    button {
      background: none;
      border: 1px solid #555;
      border-radius: 999px;
      color: inherit;
      font: inherit;
      padding: 0.1rem 0.6rem;
      cursor: pointer;
    }
    button.on {
      background: #b33;
      border-color: #b33;
    }
  `;

  @state() private current = variant();
  @state() private failing = false;

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.key);
  }

  override disconnectedCallback(): void {
    window.removeEventListener("keydown", this.key);
    super.disconnectedCallback();
  }

  private key = (event: KeyboardEvent) => {
    const at = event.composedPath()[0] as HTMLElement;
    if (at.closest?.("input, textarea, select, [contenteditable]")) return;
    if (event.key === "ArrowLeft") this.step(-1);
    if (event.key === "ArrowRight") this.step(1);
  };

  private step(by: number) {
    const at = VARIANTS.findIndex((v) => v.key === this.current);
    this.current = VARIANTS[(at + by + VARIANTS.length) % VARIANTS.length].key;
    const url = new URL(location.href);
    url.searchParams.set("variant", this.current);
    history.replaceState(null, "", url);
    window.dispatchEvent(new Event("prototype-variant"));
  }

  private toggle() {
    this.failing = !this.failing;
    window.dispatchEvent(new CustomEvent("prototype-camera", { detail: this.failing }));
  }

  override render() {
    const v = VARIANTS.find((x) => x.key === this.current)!;
    return html`
      <button @click=${() => this.step(-1)}>←</button>
      <span>${v.key} (${v.name})</span>
      <button @click=${() => this.step(1)}>→</button>
      <button class=${this.failing ? "on" : ""} @click=${this.toggle}>
        camera ${this.failing ? "fails" : "answers"}
      </button>
    `;
  }
}
