/**
 * Reading a `/review` back: what the netlist pane says and what the canvas
 * lights.
 *
 * This is the feature the rest of the editor exists to serve (EDITOR.md).
 * Airolo's WX310 composes 19 transits and 33 concurrent pairs out of four
 * turnouts and a crossing, and nobody can confirm 33 pairs by reading them. A
 * stated reason can be checked against the picture, so a transit names the
 * symbol it shares with each rival and a symbol names the leg each transit
 * through it takes.
 *
 * Nothing here derives anything. Every fact comes out of the answer the store
 * gave, which is what keeps a second union-find out of the front end.
 */

import { minted } from "./naming.js";
import type { Review } from "./store.js";

/** A symbol lit whole, having no leg of its own the artwork draws: a joiner,
 *  a block end, the generic connection box. */
export const WHOLE = "*";

/** Which transit is selected, as the connection and the name within it. */
export interface Chosen {
  connection: string;
  transit: string;
}

/**
 * What the canvas lights for a chosen transit: each symbol on its way, at the
 * legs the way takes, and the two block ends it runs between.
 *
 * The block ends are not on the way — derivation stops walking at a block —
 * but they are what the transit joins, and lighting them is what makes the
 * lit run read as one movement rather than as scattered frogs.
 */
export function lit(
  review: Review,
  chosen: Chosen | null,
): Map<string, Set<string>> {
  const found = new Map<string, Set<string>>();
  if (chosen === null) return found;
  const transit =
    review.explain?.connections[chosen.connection]?.transits[chosen.transit];
  if (transit === undefined) return found;
  const light = (symbol: string, leg: string) => {
    const legs = found.get(symbol) ?? new Set<string>();
    legs.add(leg);
    found.set(symbol, legs);
  };
  for (const [symbol, leg] of transit.way) light(symbol, leg === "" ? WHOLE : leg);
  for (const end of transit.ends) light(end.split(".")[0]!, WHOLE);
  return found;
}

/**
 * The block ends carrying no signal: those a train can never be let out of,
 * because no transit leaves them.
 *
 * A block shows a signal at each end, and at a siding's blind end that signal
 * could only ever be red — Claro 4's B end runs into a buffer stop
 * (EDITOR.md#symbol-geometry). Which ends those are is the derived layout's
 * answer: an end appears in a transit or it does not, and joints are transits
 * too, so this one field is the whole of it and no topology is computed here.
 *
 * An end is only dark once its pin is satisfied. An unwired end is in no
 * transit either, but it is unfinished rather than blind, and a block whose
 * signals vanished the moment it was dropped — the palette tile and the ghost
 * having just shown both — would read as a fault in the drawing rather than a
 * fact about it. A drawing that does not derive has no answer at all, and
 * every signal stays.
 *
 * Keyed by symbol, as `lit` is, so the canvas asks per symbol as it draws.
 */
export function dark(review: Review): Map<string, Set<string>> {
  const found = new Map<string, Set<string>>();
  const layout = review.layout;
  if (layout === null) return found;
  const routed = new Set<string>();
  for (const connection of Object.values(layout.connections)) {
    for (const ends of Object.values(connection.transits)) {
      for (const end of ends) routed.add(end);
    }
  }
  const red = new Set(review.red_pins);
  for (const block of Object.keys(layout.blocks)) {
    for (const end of ["A", "B"]) {
      const pin = `${block}.${end}`;
      if (routed.has(pin) || red.has(pin)) continue;
      const ends = found.get(block) ?? new Set<string>();
      ends.add(end);
      found.set(block, ends);
    }
  }
  return found;
}

/**
 * The portals whose label pairs with nothing, each with the label it wears.
 *
 * A portal is paired by label with exactly one other, and the store's review
 * names every label not worn by exactly two, with the portals wearing it
 * (EDITOR.md#implementation). This turns that answer inside out — keyed by
 * symbol, as `lit` and `dark` are — so the canvas asks per symbol as it draws.
 *
 * Which labels pair is not worked out here. A label worn three times is on all
 * three portals and none of them is the odd one out, so every portal wearing it
 * is marked, which is what the store already says.
 */
export function unpaired(review: Review): Map<string, string> {
  const found = new Map<string, string>();
  for (const { label, portals } of review.unpaired_portals) {
    for (const portal of portals) found.set(portal, label);
  }
  return found;
}

/** One rival of a chosen transit: whether the two run together, and where a
 *  refusal comes from. */
export interface Against {
  transit: string;
  concurrent: boolean;
  /** The symbols the two ways share that stop them, empty where they run. */
  shared: string[];
}

/** Every other transit at a connection, against a chosen one. */
export function against(
  review: Review,
  connection: string,
  transit: string,
): Against[] {
  const derived = review.layout?.connections[connection];
  if (derived === undefined || !(transit in derived.transits)) return [];
  return Object.keys(derived.transits)
    .filter((other) => other !== transit)
    .map((other) => ({
      transit: other,
      ...verdict(review, connection, transit, other),
    }));
}

/** One transit through a symbol, and the legs of that symbol it takes.
 *  `WHOLE` where the symbol has no legs to take — a joiner is passed through,
 *  and the store says so with an empty leg name. */
export interface Through {
  connection: string;
  transit: string;
  legs: string[];
}

/** Every transit whose way crosses a symbol. The inverse of choosing a
 *  transit: the drawing is read from the frog outwards. */
export function through(review: Review, symbol: string): Through[] {
  const found: Through[] = [];
  for (const [connection, explained] of Object.entries(
    review.explain?.connections ?? {},
  )) {
    for (const [transit, { way }] of Object.entries(explained.transits)) {
      const legs = way
        .filter(([crossed]) => crossed === symbol)
        .map(([, leg]) => (leg === "" ? WHOLE : leg));
      if (legs.length > 0) found.push({ connection, transit, legs });
    }
  }
  return found;
}

/**
 * Whether a symbol routes the ways that cross it, or is only passed through.
 *
 * A joiner — a bend or a portal — takes no leg of its own, so there is nothing
 * about it to inspect: no leg to name, and no pair it could hold apart. The
 * inspector is the inverse of choosing a transit, and inverting a symbol that
 * decides nothing answers nothing.
 */
export function routes(crossing: Through[]): boolean {
  return crossing.some(({ legs }) => legs.some((leg) => leg !== WHOLE));
}

/** Two transits through one symbol, and whether they run together. */
export interface Pair {
  one: string;
  two: string;
  concurrent: boolean;
  shared: string[];
  /** The legs of the selected symbol each of the two takes. */
  legs: [string[], string[]];
}

/**
 * Every pair among the transits through a symbol, split into those that can
 * run together and those that cannot.
 *
 * What blocks a pair need not be the symbol selected — two ways over one
 * diamond each cross a turnout as well — so `shared` names whatever does. The
 * legs are what makes the claim checkable: a pair that shares a leg here can
 * never run, and a pair on different legs is the symbol's own concurrency
 * speaking.
 */
export function amongst(review: Review, symbol: string): Pair[] {
  const crossing = through(review, symbol);
  const pairs: Pair[] = [];
  for (let i = 0; i < crossing.length; i++) {
    for (let j = i + 1; j < crossing.length; j++) {
      const [one, two] = [crossing[i]!, crossing[j]!];
      if (one.connection !== two.connection) continue;
      pairs.push({
        one: one.transit,
        two: two.transit,
        legs: [one.legs, two.legs],
        ...verdict(review, one.connection, one.transit, two.transit),
      });
    }
  }
  return pairs;
}

/** A name the drawing writes twice, or two names it writes on one connection.
 *  Either way derivation refuses, and this says where to look. */
export interface Clash {
  kind: "duplicate" | "disagreement";
  names: string[];
  /** Where each connection involved is: a junction's symbols, or a joint's
   *  two block ends, which is all a joint has to point at. */
  where: string[][];
}

/**
 * The name collisions and the split-junction duplicates, worked out from what
 * the drawing writes rather than from the refusal.
 *
 * Derivation reports the first thing wrong and stops, and a duplicate name is
 * worse than that: two junctions both called `airolo` derive as one
 * connection, which is a wrong netlist rather than a refused one.
 *
 * A collision the editor minted is not one of these. `settle` re-mints the
 * duplicate a split made and collapses the names a merge left (naming.ts), so
 * either is gone by the next review, and reporting it in between would show
 * the user a finding the editor is in the middle of fixing itself. What is
 * left is exactly the collisions a person typed and has to settle.
 */
export function clashes(review: Review): Clash[] {
  const connections = [
    ...review.junctions.map((one) => ({ ...one, where: one.symbols })),
    ...review.joints.map((one) => ({ ...one, where: [...one.ends] })),
  ].map((one) => ({ ...one, typed: one.names.filter((name) => !minted(name)) }));
  const found: Clash[] = connections
    .filter((one) => one.typed.length > 1)
    .map((one) => ({
      kind: "disagreement" as const,
      names: one.typed,
      where: [one.where],
    }));
  const byName = new Map<string, string[][]>();
  for (const one of connections) {
    if (one.name === null || minted(one.name)) continue;
    byName.set(one.name, [...(byName.get(one.name) ?? []), one.where]);
  }
  for (const [name, where] of byName) {
    if (where.length > 1) found.push({ kind: "duplicate", names: [name], where });
  }
  return found;
}

/** Whether two transits at one connection run together, and where the refusal
 *  comes from where they do not. The layout states the outcome and the
 *  explanation states the reason, and neither is worked out here. */
function verdict(
  review: Review,
  connection: string,
  transit: string,
  other: string,
): { concurrent: boolean; shared: string[] } {
  const concurrent = (
    review.layout?.connections[connection]?.concurrent ?? []
  ).some((pair) => pair.includes(transit) && pair.includes(other));
  const shared =
    (review.explain?.connections[connection]?.exclusive ?? []).find(
      (pair) =>
        pair.transits.includes(transit) && pair.transits.includes(other),
    )?.shared ?? [];
  return { concurrent, shared: concurrent ? [] : shared };
}
