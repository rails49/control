/**
 * The palette: one tile per placeable kind (#52's `PLACEABLE`), each of them a
 * thing to drag onto the canvas.
 *
 * Pressing a tile begins the drag and nothing else — no tile is ever armed, so
 * nothing about this component changes what a click on the canvas means
 * (EDITOR.md#palette). Where the pointer goes after that is the canvas's, and
 * whether the drag ends in a symbol is the editor's.
 *
 * Signals and sensors are not here. Every block has both at both ends, so there
 * is nothing to place. Nor is the free-standing bend: it is placed by clicking
 * empty canvas while drawing a wire. Each kind is drawn one way, so a tile shows
 * exactly what a drop will place — which is why the tiles carry no names, only
 * the word in their title for anyone who wants it.
 */

import { LitElement, html } from "lit";
import { customElement } from "lit/decorators.js";

import type { Kind } from "../symbols.generated.js";
import { FOOTPRINTS, transformOf } from "../model/geometry.js";
import { artwork, DEFS, PALETTE, TILE } from "../render/artwork.js";
import { paletteStyles } from "./tc-palette.styles.js";

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

  override render() {
    return html`
      <h2>Symbols</h2>
      <!-- One definition for all the tiles: an id is looked up across the whole
           tree, not per svg, so repeating it in each tile would repeat the id. -->
      <svg class="defs" aria-hidden="true"><defs>${DEFS}</defs></svg>
      ${PALETTE.map((group) => this.group(group))}
      <p class="hint">drag a symbol onto the sheet</p>
      <p class="hint">
        <kbd>r</kbd> rotate · <kbd>f</kbd> flip · <kbd>esc</kbd> cancel
      </p>
    `;
  }

  /**
   * One group of the palette, laid two tiles to a row. A group of one takes
   * the whole width, which is what a block's 6x1 tile wants: at half the pane
   * it would be drawn smaller than every other symbol, and the tiles are all
   * at one grid square (EDITOR.md).
   *
   * The groups are told apart by the space between them and nothing else. The
   * tiles carry no names, so a heading here would be the only word in the
   * palette and would name a category the symbols already show.
   */
  private group(kinds: readonly Kind[]) {
    return html`
      <div class=${kinds.length === 1 ? "group wide" : "group"}>
        ${kinds.map((kind) => this.tile(kind))}
      </div>
    `;
  }

  /**
   * A tile is a button so that it is reachable and named without a mouse, but
   * the gesture that places is the pointer press: a drag has to begin before
   * the button would have decided it was a click.
   */
  private tile(kind: Kind) {
    const { w, h } = FOOTPRINTS[kind];
    const spec = TILE[kind];
    return html`
      <button
        @pointerdown=${(event: PointerEvent) => this.take(kind, event)}
        title=${TITLES[kind]}
        aria-label=${TITLES[kind]}
      >
        <svg viewBox=${`-0.2 -0.2 ${w + 0.4} ${h + 0.4}`}>
          <g transform=${transformOf(spec)}>${artwork(spec)}</g>
        </svg>
      </button>
    `;
  }

  /** Only the left button starts a drag; the right one belongs to whatever
   *  menu the browser or the editor puts there. */
  private take(kind: Kind, event: PointerEvent): void {
    if (event.button !== 0) return;
    event.preventDefault();
    this.dispatchEvent(
      new CustomEvent<Kind>("take", {
        detail: kind,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-palette": TcPalette;
  }
}
