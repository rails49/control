/**
 * The three dividers outside the run view: the size a person dragged each
 * to ([#1401](https://github.com/rails49/control/issues/1401)). The run
 * view's two are `pane.ts`'s.
 *
 * The edit view's palette has one on its right. It sets the palette's
 * width, measured from the view's left edge. The netlist has one on its
 * left while it is open. It sets the netlist's width, measured from the
 * view's right edge.
 *
 * The stock view's is the space between its list box and its editor box. It
 * sets the list box's width, and the point it is dragged to is the middle
 * of the space.
 *
 * Each size is held to a least, and to a greatest that leaves the part on
 * the divider's other side a least of its own (`LIMITS`). The edit view's
 * two are each held against the view's whole width here. With the netlist
 * open the view's stylesheet holds the two against each other, so the
 * drawing keeps its least width (`ui/tc-editor.styles.ts`).
 *
 * Each size is kept in the browser under its own key. It is not on the bus
 * and not in the store. The size line and the store are look's
 * (`dividerSizeAt`, `keptDivider`, `keepDivider`).
 */

import { dividerSizeAt, keepDivider, keptDivider } from "@rails49/look";

import type { Point } from "./geometry.js";
import { DRAWING, LEAST } from "./pane.js";

/** The dividers: the palette's, the netlist's and the stock view's. */
export type Divider = "palette" | "netlist" | "stock";

/** Each divider's limits in CSS pixels: the least size of the part it sets,
 *  and what that part leaves the part on the divider's other side. */
export const LIMITS: Record<Divider, { least: number; leaves: number }> = {
  palette: { least: LEAST, leaves: DRAWING.left },
  netlist: { least: 192, leaves: DRAWING.left },
  stock: { least: 300, leaves: 320 },
};

/** The space in CSS pixels left of the stock view's list box, between its
 *  two boxes, and right of its editor box. */
export const SPACE = 16;

/** The size in CSS pixels a divider at a client point sets, held to its
 *  limits. */
export function sizeAt(divider: Divider, view: DOMRect, at: Point): number {
  if (divider === "palette") return dividerSizeAt(view, at, "left", LIMITS.palette);
  if (divider === "netlist") return dividerSizeAt(view, at, "right", LIMITS.netlist);
  const list = {
    left: view.left + 1.5 * SPACE,
    right: view.right - 1.5 * SPACE,
    top: view.top,
    bottom: view.bottom,
    width: view.width - 3 * SPACE,
    height: view.height,
  };
  return dividerSizeAt(list, at, "left", LIMITS.stock);
}

function key(divider: Divider): string {
  return `tc49.${divider}`;
}

/** The size this browser keeps for a divider, `null` for none. */
export function kept(divider: Divider): number | null {
  return keptDivider(key(divider));
}

export function keep(divider: Divider, size: number): void {
  keepDivider(key(divider), size);
}
