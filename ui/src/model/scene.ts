/**
 * What the panel's static view derives from the drawing: the fitted viewBox,
 * the pose of a direction arrow, and which symbol an address is worn by. Pure
 * reading of the document — no DOM, so it lives here and not in the component
 * (README.md).
 */

import type { Position } from "../symbols.generated.js";
import { pinsOf, type Drawing, type SymbolSpec } from "./drawing.js";
import { anchorOf, centreOf, type Point } from "./geometry.js";
import { blockOf, endOf, type EndRef } from "./panel.js";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Around the drawing: one square each side, half more top and bottom so a
 *  marker's note under a block end stays on the sheet. */
const MARGIN = 1;
const HEADROOM = 1.5;

/** The whole drawing with a margin, as a fixed viewBox: the panel is a
 *  watching surface, so there is no zoom or pan to hold. */
export function fitBox(drawing: Drawing): Box {
  const points = Object.values(drawing.symbols).flatMap((spec: SymbolSpec) =>
    pinsOf(spec).map((pin) => anchorOf(spec, pin)),
  );
  if (points.length === 0) return { x: -1, y: -1, w: 16, h: 11 };
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const [x, y] = [Math.min(...xs) - MARGIN, Math.min(...ys) - HEADROOM];
  return {
    x,
    y,
    w: Math.max(...xs) - x + MARGIN,
    h: Math.max(...ys) - y + HEADROOM,
  };
}

/** How far along the track from a block's centre the arrow sits. */
const AHEAD = 1.1;

export interface Pose {
  x: number;
  y: number;
  /** Degrees, as SVG `rotate` takes it. */
  angle: number;
}

/** Where a block's direction arrow goes and which way it points: on the
 *  track, ahead of the block's centre, at the end the train faces. */
export function arrowPose(spec: SymbolSpec, toward: string): Pose {
  const centre = centreOf(spec);
  const nose = anchorOf(spec, toward);
  const [dx, dy] = [nose.x - centre.x, nose.y - centre.y];
  const length = Math.hypot(dx, dy);
  const at = Math.min(AHEAD, length) / length;
  return {
    x: centre.x + dx * at,
    y: centre.y + dy * at,
    angle: (Math.atan2(dy, dx) * 180) / Math.PI,
  };
}

/** Where a block end sits on the sheet, or nothing where the drawing has no
 *  such symbol or pin. Request markers and the drag's rings both ask this, so
 *  an end ref is read apart in one place. */
export function anchorAt(drawing: Drawing, end: EndRef): Point | null {
  const spec = drawing.symbols[blockOf(end)];
  if (spec === undefined || !pinsOf(spec).includes(endOf(end))) return null;
  return anchorOf(spec, endOf(end));
}

/**
 * Where each point on the sheet lies, keyed by symbol, from the positions the
 * alignment command commanded by address (ui/PANEL.md, #98).
 *
 * A point is addressed rather than named
 * ([ADR-0022](../../../docs/adr/0022-a-symbol-carries-its-hardware-address.md)),
 * so the drawing is what turns an address back into a symbol to draw. Two
 * points may wear one address, and then they answer to one accessory output
 * and lie the same way.
 *
 * An address no symbol wears is left out. The railroad is wired by hand and
 * the drawing is edited by hand, so the two can disagree; that is one point
 * the panel cannot show rather than a panel that cannot draw.
 */
export function positionsBySymbol(
  drawing: Drawing,
  commanded: ReadonlyMap<string, Position>,
): Map<string, Position> {
  const found = new Map<string, Position>();
  for (const [name, spec] of Object.entries(drawing.symbols)) {
    const position =
      spec.addr === undefined ? undefined : commanded.get(spec.addr);
    if (position !== undefined) found.set(name, position);
  }
  return found;
}
