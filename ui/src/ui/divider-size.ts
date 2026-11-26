/**
 * A divider's size, handed to its view's stylesheet as a custom property
 * ([#1401](https://github.com/rails49/control/issues/1401)): the palette's
 * and the netlist's in the edit view, and the list's in the stock view.
 *
 * What size a point means and where it is kept are `model/divider.ts`'s. A
 * view calls `setKept` when it comes onto the page and `moved` when its
 * `look-gap` says it was dragged.
 */

import { keep, kept, sizeAt, type Divider } from "../model/divider.js";
import type { Point } from "../model/geometry.js";

/** The custom property each divider's size is handed over as. */
const PROPERTY: Record<Divider, string> = {
  palette: "--palette-size",
  netlist: "--netlist-size",
  stock: "--list-size",
};

/** Hand a view's stylesheet the size this browser keeps for a divider. With
 *  none kept nothing is set, and the stylesheet's own size holds. */
export function setKept(view: HTMLElement, divider: Divider): void {
  const size = kept(divider);
  if (size !== null) view.style.setProperty(PROPERTY[divider], `${size}px`);
}

/** A view's divider dragged to a client point: the size that point means in
 *  the view's box, handed to the stylesheet and kept. */
export function moved(view: HTMLElement, divider: Divider, at: Point): void {
  const size = sizeAt(divider, view.getBoundingClientRect(), at);
  view.style.setProperty(PROPERTY[divider], `${size}px`);
  keep(divider, size);
}
