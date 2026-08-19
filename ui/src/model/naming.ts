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
 * **A typed name is replaced on load.** Opening a drawing re-mints every
 * connection name it carries, so no open drawing holds one a person typed
 * ([ADR-0023](../../../docs/adr/0023-internal-names-are-minted-and-hidden.md)).
 * A `connection` key is still written and still read, and a hand-written
 * drawing still loads and still derives; what changes is that the editor stops
 * honouring a typed one the moment the drawing is opened.
 *
 * **Splits and merges settle themselves.** Deleting a symbol can split a
 * junction in two, which leaves one name on both halves; wiring two together
 * merges them, which leaves both names on one junction. Derivation refuses
 * either way, and either way the editor settles it, because every name it is
 * choosing between is one it minted and nobody is reading `j7`. Which half is
 * Airolo was the one question it could not answer, and there is no longer an
 * Airolo to ask it about.
 */

import { TRANSITS } from "../symbols.generated.js";
import { wireKey, type Drawing, type SymbolSpec } from "./drawing.js";
import type { Joint, Junction, Review } from "./store.js";

const MINTED = /^j[1-9][0-9]*$/;

/** Whether a name was minted here. Only needed while loading, to tell what to
 *  replace: everything a drawing holds after that is minted. */
export function minted(name: string): boolean {
  return MINTED.test(name);
}

/**
 * Open a drawing: the settle pass, with no typed name honoured. Says whether
 * it wrote anything, which it does for every hand-written railroad.
 *
 * The re-minted document is what the editor holds from then on. It is not an
 * undo step — there is nothing to undo back to — and the drawing is marked as
 * holding unsaved edits, because it does.
 */
export function remint(drawing: Drawing, review: Review): boolean {
  return settle(drawing, forgetting(review));
}

/**
 * The review as it reads once no typed name is honoured: a junction or a joint
 * carrying one has no name at all, so the settle pass mints it a fresh one and
 * writes it over every member.
 *
 * All of a connection's names go together rather than the typed ones alone. A
 * junction wearing `airolo` and `j2` is a merge that has already happened, and
 * keeping `j2` would hand the merged throat a name half of it never wore for
 * no gain: the name is nobody's to read either way.
 *
 * A junction of one symbol is named after that symbol and writes no
 * `connection` at all, so it carries no name to replace and is left as the
 * drawing has it.
 */
function forgetting(review: Review): Review {
  return {
    ...review,
    junctions: review.junctions.map(forgotten),
    joints: review.joints.map(forgotten),
  };
}

function forgotten<One extends Junction | Joint>(one: One): One {
  return one.names.every(minted) ? one : { ...one, name: null, names: [] };
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
 * A merge leaves one name from each of the junctions it joined, and every one
 * of them is minted — a typed name does not outlive the load that read it — so
 * the lowest wins. The merged junction keeps a name it already wore and the
 * rest of the diff is names coming off.
 *
 * The names this drops are free again by the next review, which is where
 * `taken` comes from; nothing tries to reuse them within one pass.
 */
function survivor(names: string[]): string {
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

/** It shares its name with another, which derivation refuses, so it takes a
 *  fresh one. Only a minted name is re-minted: the one other name a junction
 *  can wear is its own lone symbol's key, which is not this module's to
 *  change. */
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
