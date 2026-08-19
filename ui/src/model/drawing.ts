/**
 * The drawing document, exactly as the store serves and takes it back
 * (store/DRAWING.md).
 *
 * The editor holds the document itself rather than a model of its own. A
 * second model would have to be converted both ways on every load and save,
 * and the conversion is where a symbol's comment, or a key the editor does
 * not know about, would quietly go missing.
 *
 * Nothing here derives anything. Which pin joins which is the document's, but
 * what that means — junctions, transits, what excludes what — comes from the
 * store's `/review` (EDITOR.md).
 */

import {
  PINS,
  POSITIONS,
  type Kind,
  type MotorisedKind,
  type Rotation,
} from "../symbols.generated.js";

/** A pin, written `<symbol>.<pin>`. */
export type PinRef = string;

/**
 * A wire is a pair of pins. The mapping form is for a wire that joins two
 * blocks, which is itself the connection holding their transit and so needs a
 * name.
 */
export type Wire =
  | [PinRef, PinRef]
  | { pins: [PinRef, PinRef]; connection: string };

/**
 * The kinds the editor draws, plus the generic connection symbol.
 *
 * That one is legacy and not on the palette: it has no fixed pin set, so there
 * is nothing to place, and its last user is Gotthard's Claro east, which is to
 * be redrawn from real symbols (#35). Until then a drawing that has one still
 * has to open, so it is drawn as a box with the pins it declares and no
 * turnout detail, which is exactly what it says about itself.
 */
export type AnyKind = Kind | "connection";

export interface SymbolSpec {
  kind: AnyKind;
  /** The grid cell of the symbol's top-left square. */
  at?: [number, number];
  rot?: Rotation;
  flip?: boolean;
  /** Blocks. */
  length?: number;
  sensors?: Record<string, string>;
  /** A portal's pairing label: two portals wearing one label join. */
  label?: string;
  /** What the hardware behind a motorised symbol answers to. */
  addr?: string;
  /** The junction this symbol belongs to. */
  connection?: string;
  /** Transit names, keyed by the symbol leg the way through takes. */
  names?: Record<string, string>;
  /** The generic connection symbol declares its own pins and transits. */
  pins?: string[];
  transits?: Record<string, [string, string]> | [string, string][];
  concurrent?: [string, string][];
}

/** A symbol's pins: the library's, or the ones a generic connection symbol
 *  declares for itself. */
export function pinsOf(spec: SymbolSpec): readonly string[] {
  return spec.kind === "connection" ? (spec.pins ?? []) : PINS[spec.kind];
}

/**
 * The kinds whose name is the user's to choose. A name is typed only where a
 * person has to say it out loud
 * ([ADR-0023](../../../docs/adr/0023-internal-names-are-minted-and-hidden.md)):
 * a block, which the operator names, the bus carries and a scenario places
 * trains in. Every other name is minted and hidden — a turnout and a slip are
 * addressed by `addr` rather than by their key
 * ([ADR-0022](../../../docs/adr/0022-a-symbol-carries-its-hardware-address.md)),
 * a fixed crossing has nothing to command, a pin and a terminal are wiring,
 * and a portal is known by its label. The hidden ones are still in the yaml and
 * still read in the netlist pane.
 *
 * The generic connection symbol is here because its name is the only handle on
 * it, the kind being legacy and on its way out (#35).
 */
const NAMED = new Set<AnyKind>(["block", "connection"]);

export function named(kind: AnyKind): boolean {
  return NAMED.has(kind);
}

/**
 * Whether a kind has a motor, and so carries the address hardware answers to
 * ([ADR-0022](../../../docs/adr/0022-a-symbol-carries-its-hardware-address.md)).
 * A turnout and both slips do; a fixed crossing has nothing to command and
 * takes none. The library's leg-to-position table is the roll of them, so
 * there is no second list here to fall out of step with it.
 */
export function motorised(kind: AnyKind): kind is MotorisedKind {
  return kind in POSITIONS;
}

export interface Drawing {
  drawing: string;
  units?: string;
  symbols: Record<string, SymbolSpec>;
  wires: Wire[];
}

export function emptyDrawing(name: string): Drawing {
  return { drawing: name, symbols: {}, wires: [] };
}

/** Why a name cannot name a new drawing, or `null` for one that can. It
 *  becomes `layouts/<name>.drawing.yaml`, and a taken name is refused rather
 *  than overwritten: overwriting deliberately is open-and-save. */
export function nameTrouble(name: string, taken: readonly string[]): string | null {
  if (name.includes("/")) return `'${name}' cannot name a file`;
  if (taken.includes(name)) return `'${name}' is already a railroad`;
  return null;
}

/** What the drawing schema takes as a name: not empty, and without the `.`
 *  that separates a symbol from its pin or the `/` that separates a path. */
export function isName(name: string): boolean {
  return name !== "" && !name.includes(".") && !name.includes("/");
}

/**
 * Why a symbol name will not do, or `null` for one that will. The properties
 * dialog is the only place a symbol name is typed, so it is the only place a
 * collision can be made, and it asks this before it closes: a refusal read
 * across the screen was telling the author about a keystroke they had just
 * made (ADR-0023).
 *
 * `was` is the name being replaced, so applying a dialog nothing was typed
 * into is not a rename onto a name the drawing already has. `taken` is every
 * name the drawing holds, `was` among them.
 */
export function symbolTrouble(
  name: string,
  was: string,
  taken: readonly string[],
): string | null {
  if (name === "") return "a symbol needs a name";
  if (!isName(name)) return `'${name}' cannot name a symbol`;
  if (name !== was && taken.includes(name)) return `'${name}' is already taken`;
  return null;
}

export function clone(drawing: Drawing): Drawing {
  return structuredClone(drawing);
}

export function wirePins(wire: Wire): [PinRef, PinRef] {
  return Array.isArray(wire) ? wire : wire.pins;
}

export function wireConnection(wire: Wire): string | undefined {
  return Array.isArray(wire) ? undefined : wire.connection;
}

/** The two pins a wire joins, sorted, which is how one is identified. */
export function wireKey(wire: Wire): string {
  return [...wirePins(wire)].sort().join(" ");
}

export function symbolOf(pin: PinRef): string {
  return pin.slice(0, pin.indexOf("."));
}

export function pinName(pin: PinRef): string {
  return pin.slice(pin.indexOf(".") + 1);
}
