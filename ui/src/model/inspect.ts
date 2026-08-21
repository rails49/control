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

import { symbolOf, wireKey, wirePins, type Wire } from "./drawing.js";
import type { Review, Transit } from "./store.js";

/** A symbol lit whole, having no leg of its own the artwork draws: a joiner,
 *  a block end, the generic connection box. */
export const WHOLE = "*";

/** Which transit is selected, as the connection and the name within it. */
export interface Chosen {
  connection: string;
  transit: string;
}

/**
 * What the canvas lights for a set of ways: each symbol on one, at the legs
 * that way takes, and the two block ends it runs between.
 *
 * The block ends are not on the way — derivation stops walking at a block —
 * but they are what a transit joins, and lighting them is what makes the lit
 * run read as one movement rather than as scattered frogs.
 *
 * A way, rather than a choice in the netlist pane: the ways behind a refusal
 * arrive already walked (`review.offending`), and both callers want the same
 * answer in the same shape.
 */
export function lit(ways: readonly Transit[]): Map<string, Set<string>> {
  const found = new Map<string, Set<string>>();
  const light = (symbol: string, leg: string) => {
    const legs = found.get(symbol) ?? new Set<string>();
    legs.add(leg);
    found.set(symbol, legs);
  };
  for (const { ends, way } of ways) {
    for (const [symbol, leg] of way) light(symbol, leg === "" ? WHOLE : leg);
    for (const end of ends) light(end.split(".")[0]!, WHOLE);
  }
  return found;
}

/**
 * The wires one way is drawn over, as the keys `wireKey` gives them.
 *
 * The rule: a wire is on a way when **both** of its pins are in the way's two
 * ends together with every pin of every symbol the way crosses. A pin names
 * the symbol carrying it, so "a pin of a symbol on the way" is read off the
 * pin rather than out of a pin list, and the wires are all that is needed.
 *
 * A transcription of the store's own rule — `Drawing.wires_on`, which is how
 * derivation finds a joint's chain and names it — so whoever changes one
 * changes the other. `tests/store/test_drawing.py` proves it exact against
 * the hops the walk takes, on every committed railroad, which is what this
 * cheaper copy rests on.
 *
 * Per way, never over a union of everything lit. A wire between two non-block
 * symbols is what merges them into one junction, so a union has no transit to
 * attribute a wire to — and the panel colours each wire by the state of the
 * transit carrying it.
 */
export function wiresOn(way: Transit, wires: readonly Wire[]): string[] {
  const held = new Set<string>(way.ends);
  const crossed = new Set(way.way.map(([symbol]) => symbol));
  const on = (pin: string) => held.has(pin) || crossed.has(symbolOf(pin));
  return wires.filter((wire) => wirePins(wire).every(on)).map(wireKey);
}

/** The wires a set of ways is drawn over, together: the companion to `lit`,
 *  for a caller painting every lit way in one colour. Still applied one way
 *  at a time, the union being taken of the answers rather than of the ways. */
export function litWires(
  ways: readonly Transit[],
  wires: readonly Wire[],
): Set<string> {
  return new Set(ways.flatMap((way) => wiresOn(way, wires)));
}

/**
 * A drawing's wires in the order they are drawn, the lit ones last.
 *
 * A lit wire drawn under an unlit one it crosses is half hidden, and SVG has
 * no z beyond the order the lines are emitted in — the ordering the artwork
 * already applies to lit legs, applied to the wires between symbols.
 *
 * The caller says what lit means, since the editor's canvas lights the way a
 * refusal or a netlist choice is about and the panel lights a route in two
 * colours. The wires are all this needs: where the two ends of a line are is
 * the caller's own lookup, and the ordering does not depend on it. The given
 * array is left alone.
 */
export function litLast(
  wires: readonly Wire[],
  alight: (wire: Wire) => boolean,
): Wire[] {
  return [...wires].sort(
    (one, two) => Number(alight(one)) - Number(alight(two)),
  );
}

/** The way a transit chosen in the netlist pane takes, as the one way to
 *  light. Empty where nothing is chosen, and where the choice is stale —
 *  every edit re-reviews, and a transit can go with the wire that made it. */
export function chosenWay(review: Review, chosen: Chosen | null): Transit[] {
  if (chosen === null) return [];
  const transit =
    review.explain?.connections[chosen.connection]?.transits[chosen.transit];
  return transit === undefined ? [] : [transit];
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
