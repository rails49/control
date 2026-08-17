/**
 * The palette: one tile per placeable kind (#52's `PLACEABLE`).
 *
 * Signals and sensors are not here. Every block has both at both ends, so
 * there is nothing to place. Nor is the free-standing bend: it is placed by
 * clicking empty canvas while drawing a wire. Each kind is drawn one way, so a
 * tile shows exactly what a click will place.
 */

import { LitElement, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import type { Kind } from "../symbols.generated.js";
import { FOOTPRINTS, transformOf } from "../model/geometry.js";
import { artwork, DEFS, PALETTE, TILE } from "../render/artwork.js";
import { paletteStyles } from "./styles.js";

const TITLES: Record<Kind, string> = {
  block: "Block",
  terminal: "Terminal",
  portal: "Portal",
  pin: "Bend",
  turnout: "Turnout",
  crossing: "Crossing",
  crossing_90: "90° crossing",
  crossing_90d: "90° crossing, diagonal",
  single_slip: "Single slip",
  double_slip: "Double slip",
};

@customElement("tc-palette")
export class TcPalette extends LitElement {
  static override styles = paletteStyles;

  /** The kind the next click on the canvas places, if any. */
  @property({ attribute: false }) armed: Kind | null = null;

  override render() {
    return html`
      <h2>Symbols</h2>
      <!-- One definition for all the tiles: an id is looked up across the whole
           tree, not per svg, so repeating it in each tile would repeat the id. -->
      <svg class="defs" aria-hidden="true"><defs>${DEFS}</defs></svg>
      ${PALETTE.map((kind) => this.tile(kind))}
    `;
  }

  private tile(kind: Kind) {
    const { w, h } = FOOTPRINTS[kind];
    const spec = TILE[kind];
    return html`
      <button
        aria-pressed=${this.armed === kind}
        @click=${() => this.arm(kind)}
        title=${TITLES[kind]}
      >
        <svg viewBox=${`-0.2 -0.2 ${w + 0.4} ${h + 0.4}`}>
          <g transform=${transformOf(spec)}>${artwork(spec)}</g>
        </svg>
        <span>${TITLES[kind]}</span>
      </button>
    `;
  }

  /** Clicking the armed tile disarms it, so the palette is a toggle and the
   *  canvas is never left waiting for a placement nobody wants. */
  private arm(kind: Kind): void {
    const armed = this.armed === kind ? null : kind;
    this.dispatchEvent(
      new CustomEvent("arm", { detail: armed, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-palette": TcPalette;
  }
}
