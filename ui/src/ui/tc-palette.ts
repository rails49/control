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
 *
 * The fifth group is the widgets: a button, a toggle and a text (ADR-0087).
 * They are dragged out the same way, and the editor names them as it places
 * them. A tile shows the face a new one has (#939): a button, a toggle and
 * the word `text`.
 */

import { LitElement, html } from "lit";
import { customElement } from "lit/decorators.js";

import type { Kind } from "../symbols.generated.js";
import type { WidgetKind } from "../model/drawing.js";
import { FOOTPRINTS, transformOf } from "../model/geometry.js";
import { WIDGET_KINDS, widgetFootprint } from "../model/widgets.js";
import { artwork, DEFS, PALETTE, TILE, widgetSample } from "../render/artwork.js";
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

const WIDGET_TITLES: Record<WidgetKind, string> = {
  text: "Text",
  button: "Button",
  toggle: "Toggle",
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
      <div class="group widgets">
        ${WIDGET_KINDS.map((kind) => this.widgetTile(kind))}
      </div>
      <p class="hint">drag a symbol onto the sheet</p>
      <p class="hint keys">
        <span><kbd>r</kbd> rotate</span>
        <span><kbd>f</kbd> flip</span>
        <span><kbd>esc</kbd> cancel</span>
      </p>
    `;
  }

  /**
   * One group of the palette, a box of its own laid two tiles to a row. A
   * group of one takes the whole width, which is what a block's 6x1 tile
   * wants: at half the pane it would be drawn smaller than every other symbol,
   * and the tiles are all at one grid square (EDITOR.md). A row's first tile
   * starts a new row, so a row of one leaves the right column empty.
   *
   * The boxes carry no headings. The tiles carry no names, so a heading here
   * would be the only word in the palette and would name a category the
   * symbols already show.
   */
  private group(rows: readonly (readonly Kind[])[]) {
    const wide = rows.length === 1 && rows[0]!.length === 1;
    return html`
      <div class=${wide ? "group wide" : "group"}>
        ${rows.map((row) => row.map((kind, i) => this.tile(kind, i === 0)))}
      </div>
    `;
  }

  /**
   * A tile is a button so that it is reachable and named without a mouse, but
   * the gesture that places is the pointer press: a drag has to begin before
   * the button would have decided it was a click.
   */
  private tile(kind: Kind, first: boolean) {
    const { w, h } = FOOTPRINTS[kind];
    const spec = TILE[kind];
    return html`
      <button
        class=${first ? "first" : ""}
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

  /** A widget's tile: the face a new one has. */
  private widgetTile(kind: WidgetKind) {
    const [w, h] = widgetFootprint(kind);
    return html`
      <button
        @pointerdown=${(event: PointerEvent) => this.take(kind, event)}
        title=${WIDGET_TITLES[kind]}
        aria-label=${WIDGET_TITLES[kind]}
      >
        <svg viewBox=${`-0.2 -0.2 ${w + 0.4} ${h + 0.4}`}>
          <g class=${`widget ${kind}`}>${widgetSample(kind, [0, 0])}</g>
        </svg>
      </button>
    `;
  }

  /** Only the left button starts a drag; the right one belongs to whatever
   *  menu the browser or the editor puts there. */
  private take(kind: Kind | WidgetKind, event: PointerEvent): void {
    if (event.button !== 0) return;
    event.preventDefault();
    this.dispatchEvent(
      new CustomEvent<Kind | WidgetKind>("take", {
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
