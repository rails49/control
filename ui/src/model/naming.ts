/**
 * Connection names, minted and written into the drawing.
 *
 * A connection's name is authored, never derived (store/DRAWING.md), so one
 * has to come from somewhere when nobody has typed one. Names are minted `j1`,
 * `j2` and written at once, so a junction always has a valid name and nothing
 * interrupts a sketch. Naming a junction writes `connection:` onto every
 * member; naming a bare wire between two blocks writes it onto the wire, that
 * wire being the connection.
 *
 * Which junctions and joints exist is the store's answer (`/review`), not a
 * second union-find here. What this module decides is only what they are
 * called.
 *
 * **Splits and merges resolve by provenance.** Deleting a symbol can split a
 * junction in two and wiring two together merges them, and either way a name
 * ends up on both halves, which derivation refuses as a duplicate. A minted
 * name is re-minted silently on both sides, because nobody is reading `j7`. A
 * name someone typed stays where it is, and the refusal is reported: choosing
 * which half is Airolo is not the editor's decision to make.
 */

import { wireKey, type Drawing, type SymbolSpec } from "./drawing.js";
import type { Joint, Junction, Review } from "./store.js";

const MINTED = /^j[1-9][0-9]*$/;

/** Whether a name was minted here, which is what makes it safe to re-mint. */
export function minted(name: string): boolean {
  return MINTED.test(name);
}

/**
 * Give every unnamed junction and joint a name, and re-mint the minted names a
 * split or a merge left on two of them. Says whether it wrote anything.
 */
export function settle(drawing: Drawing, review: Review): boolean {
  const taken = new Set(
    [...review.junctions, ...review.joints].flatMap((one) =>
      one.name === null ? one.names : [one.name, ...one.names],
    ),
  );
  let wrote = false;
  for (const junction of review.junctions) {
    if (wants(junction) || clashes(junction, review)) {
      nameJunction(drawing, junction.symbols, mint(taken));
      wrote = true;
    }
  }
  for (const joint of review.joints) {
    if (wants(joint) || clashes(joint, review)) {
      nameJoint(drawing, joint, mint(taken));
      wrote = true;
    }
  }
  return wrote;
}

/** Write a name onto a junction: every one of its symbols says it. */
export function nameJunction(
  drawing: Drawing,
  symbols: string[],
  name: string,
): void {
  for (const symbol of symbols) {
    const spec: SymbolSpec | undefined = drawing.symbols[symbol];
    if (spec !== undefined) spec.connection = name;
  }
}

/** Write a name onto a joint. The name goes on one segment of the chain and
 *  the others give theirs up, since two names on one joint are refused. */
export function nameJoint(drawing: Drawing, joint: Joint, name: string): void {
  const chain = new Set(joint.wires.map((wire) => [...wire].sort().join(" ")));
  let written = false;
  drawing.wires = drawing.wires.map((wire) => {
    if (!chain.has(wireKey(wire))) return wire;
    const pins = Array.isArray(wire) ? wire : wire.pins;
    if (written) return pins;
    written = true;
    return { pins, connection: name };
  });
}

/** Nobody has named it, and nobody typed anything to disagree about. */
function wants(one: Junction | Joint): boolean {
  return one.name === null && one.names.length === 0;
}

/** It shares its name with another, which derivation refuses. Re-minted where
 *  the name was minted, left alone where someone typed it. */
function clashes(one: Junction | Joint, review: Review): boolean {
  if (one.name === null || !minted(one.name)) return false;
  const wearing = [...review.junctions, ...review.joints].filter(
    (other) => other.name === one.name,
  );
  return wearing.length > 1;
}

function mint(taken: Set<string>): string {
  for (let n = 1; ; n++) {
    const name = `j${n}`;
    if (!taken.has(name)) {
      taken.add(name);
      return name;
    }
  }
}
