/**
 * Connection names, minted and written into the drawing.
 *
 * A connection's name is authored, never derived (store/DRAWING.md), so one
 * has to come from somewhere when nobody has typed one. Names are minted `j1`,
 * `j2` and written at once, so a junction always has a valid name and nothing
 * interrupts a sketch. Naming a junction writes `connection:` onto the members
 * that declare a transit; naming a bare wire between two blocks writes it onto
 * the wire, that wire being the connection.
 *
 * Which junctions and joints exist is the store's answer (`/review`), not a
 * second union-find here. What this module decides is only what they are
 * called.
 *
 * **Splits and merges resolve by provenance.** Deleting a symbol can split a
 * junction in two, which leaves one name on both halves; wiring two together
 * merges them, which leaves both names on one junction. Derivation refuses
 * either way, and either way the editor settles it when only minted names are
 * involved, because nobody is reading `j7`. A name someone typed stays where
 * it is, and the refusal is reported: choosing which half is Airolo is not the
 * editor's decision to make.
 */

import { TRANSITS } from "../symbols.generated.js";
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
    const name = settled(junction, review, taken);
    if (name !== null) {
      nameJunction(drawing, junction.symbols, name);
      wrote = true;
    }
  }
  for (const joint of review.joints) {
    const name = settled(joint, review, taken);
    if (name !== null) {
      nameJoint(drawing, joint, name);
      wrote = true;
    }
  }
  return wrote;
}

/** The name to write, or `null` to leave it as it is: a fresh one where there
 *  is none and where a split duplicated one, the survivor where a merge left
 *  several. */
function settled(
  one: Junction | Joint,
  review: Review,
  taken: Set<string>,
): string | null {
  if (wants(one)) return mint(taken);
  if (one.names.length > 1) return survivor(one.names);
  return clashes(one, review) ? mint(taken) : null;
}

/**
 * Which of several names on one junction survives a merge.
 *
 * A merge leaves one name from each of the junctions it joined, and only a
 * typed one is a decision. Where every name is minted the lowest of them wins,
 * so the merged junction keeps a name it already wore and the rest of the diff
 * is names coming off. Where exactly one was typed it wins outright: it is the
 * only name anybody chose, and minting over it would throw away the only
 * meaningful one. Two typed names is the case the editor cannot settle, and
 * derivation refuses it.
 *
 * The names this drops are free again by the next review, which is where
 * `taken` comes from; nothing tries to reuse them within one pass.
 */
function survivor(names: string[]): string | null {
  const typed = names.filter((name) => !minted(name));
  if (typed.length > 1) return null;
  if (typed.length === 1) return typed[0]!;
  return names.reduce((one, other) => (number(one) <= number(other) ? one : other));
}

/** The number a minted name carries, `j10` being above `j9` and not below it
 *  the way sorting them as text says. */
function number(name: string): number {
  return Number(name.slice(1));
}

/**
 * Write a name onto a junction: every one of its symbols that can wear it
 * says it, and any that cannot gives one up.
 *
 * A junction is the connected group of non-block symbols, so a bend joining
 * two wires is in it — but a joiner passes a wire through and declares no
 * transit, and the drawing schema gives it no `connection` to write
 * (store/DRAWING.md). Writing one refused the whole document, and since a
 * refused drawing cannot be reviewed the editor could not say which key it
 * was. Clearing the ones that cannot wear it repairs a drawing an older
 * editor wrote.
 */
export function nameJunction(
  drawing: Drawing,
  symbols: string[],
  name: string,
): void {
  for (const symbol of symbols) {
    const spec: SymbolSpec | undefined = drawing.symbols[symbol];
    if (spec === undefined) continue;
    if (declares(spec)) spec.connection = name;
    else delete spec.connection;
  }
}

/** Whether a symbol is one the junction is made of rather than one the wire
 *  runs through. The same question the store asks to work out what a junction
 *  is called: only a symbol declaring a transit is part of the answer. */
function declares(spec: SymbolSpec): boolean {
  return spec.kind === "connection" || spec.kind in TRANSITS;
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
