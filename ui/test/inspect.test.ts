import { describe, expect, it } from "vitest";

import {
  WHOLE,
  against,
  amongst,
  clashes,
  dark,
  lit,
  routes,
  through,
} from "../src/model/inspect.js";
import type { Review } from "../src/model/store.js";

/**
 * `crossover-yard`'s scissors, as `/review` answers it. Four transits over
 * four turnouts and a diamond, with one concurrent pair: the two straights.
 * It is the derivation DRAWING.md leans on hardest, and small enough to read.
 */
function scissors(): Review {
  return {
    red_pins: [],
    junctions: [
      {
        name: "crossover",
        names: ["crossover"],
        symbols: [
          "diamond",
          "dn_e_points",
          "dn_w_points",
          "up_e_points",
          "up_w_points",
        ],
      },
    ],
    joints: [],
    layout: {
      layout: "crossover-yard",
      blocks: { dn_e: { length: 3200 } },
      connections: {
        crossover: {
          transits: {
            dn_straight: ["dn_e.A", "dn_w.B"],
            dn_to_up: ["dn_w.B", "up_e.A"],
            up_straight: ["up_e.A", "up_w.B"],
            up_to_dn: ["dn_e.A", "up_w.B"],
          },
          concurrent: [["dn_straight", "up_straight"]],
        },
      },
    },
    explain: {
      layout: "crossover-yard",
      connections: {
        crossover: {
          transits: {
            dn_straight: {
              ends: ["dn_e.A", "dn_w.B"],
              way: [
                ["dn_e_points", "straight"],
                ["dn_w_points", "straight"],
              ],
            },
            dn_to_up: {
              ends: ["dn_w.B", "up_e.A"],
              way: [
                ["dn_w_points", "diverging"],
                ["diamond", "b"],
                ["up_e_points", "diverging"],
              ],
            },
            up_straight: {
              ends: ["up_e.A", "up_w.B"],
              way: [
                ["up_e_points", "straight"],
                ["up_w_points", "straight"],
              ],
            },
            up_to_dn: {
              ends: ["dn_e.A", "up_w.B"],
              way: [
                ["dn_e_points", "diverging"],
                ["diamond", "a"],
                ["up_w_points", "diverging"],
              ],
            },
          },
          exclusive: [
            { transits: ["dn_straight", "dn_to_up"], shared: ["dn_w_points"] },
            { transits: ["dn_straight", "up_to_dn"], shared: ["dn_e_points"] },
            { transits: ["dn_to_up", "up_straight"], shared: ["up_e_points"] },
            { transits: ["dn_to_up", "up_to_dn"], shared: ["diamond"] },
            { transits: ["up_straight", "up_to_dn"], shared: ["up_w_points"] },
          ],
        },
      },
    },
    refused: null,
  };
}

describe("the way a chosen transit takes", () => {
  it("lights each symbol on the way at the leg the way takes", () => {
    const way = lit(scissors(), { connection: "crossover", transit: "up_to_dn" });
    expect(way.get("dn_e_points")).toEqual(new Set(["diverging"]));
    expect(way.get("diamond")).toEqual(new Set(["a"]));
    expect(way.get("up_w_points")).toEqual(new Set(["diverging"]));
  });

  it("lights the two block ends the transit runs between, whole", () => {
    const way = lit(scissors(), { connection: "crossover", transit: "up_to_dn" });
    expect(way.get("dn_e")).toEqual(new Set([WHOLE]));
    expect(way.get("up_w")).toEqual(new Set([WHOLE]));
  });

  it("lights a joiner whole, having no leg of its own to light", () => {
    const found = scissors();
    found.explain!.connections.crossover!.transits.dn_straight!.way = [
      ["bend_3", ""],
      ["dn_w_points", "straight"],
    ];
    const way = lit(found, { connection: "crossover", transit: "dn_straight" });
    expect(way.get("bend_3")).toEqual(new Set([WHOLE]));
  });

  it("lights nothing when nothing is chosen, or when the choice is stale", () => {
    expect(lit(scissors(), null).size).toBe(0);
    expect(
      lit(scissors(), { connection: "crossover", transit: "gone" }).size,
    ).toBe(0);
  });
});

describe("a chosen transit against the others at its connection", () => {
  it("says which run with it and which cannot, naming the symbol shared", () => {
    expect(against(scissors(), "crossover", "dn_straight")).toEqual([
      { transit: "dn_to_up", concurrent: false, shared: ["dn_w_points"] },
      { transit: "up_straight", concurrent: true, shared: [] },
      { transit: "up_to_dn", concurrent: false, shared: ["dn_e_points"] },
    ]);
  });

  it("is empty at a connection with one transit, and for one that is gone", () => {
    expect(against(scissors(), "crossover", "gone")).toEqual([]);
    expect(against(scissors(), "nowhere", "dn_straight")).toEqual([]);
  });
});

describe("the transits through a symbol", () => {
  it("names each with the leg of the symbol it takes", () => {
    expect(through(scissors(), "diamond")).toEqual([
      { connection: "crossover", transit: "dn_to_up", legs: ["b"] },
      { connection: "crossover", transit: "up_to_dn", legs: ["a"] },
    ]);
  });

  it("is empty for a symbol no transit crosses", () => {
    expect(through(scissors(), "yard_stop")).toEqual([]);
  });

  it("reports a joiner as taken whole, having no leg of its own", () => {
    // The store writes an empty leg for a bend or a portal. Left as it comes,
    // the pane prints a blank where a leg goes.
    const found = scissors();
    found.explain!.connections.crossover!.transits.dn_straight!.way = [
      ["bend_3", ""],
    ];
    expect(through(found, "bend_3")).toEqual([
      { connection: "crossover", transit: "dn_straight", legs: [WHOLE] },
    ]);
  });
});

/** The inspector is the inverse of choosing a transit, and a joiner decides
 *  nothing, so inverting one answers nothing and the pane draws no section. */
describe("whether a symbol routes what crosses it", () => {
  it("says a symbol taking legs of its own does", () => {
    expect(routes(through(scissors(), "diamond"))).toBe(true);
    expect(routes(through(scissors(), "dn_e_points"))).toBe(true);
  });

  it("says a joiner does not, being passed through", () => {
    const found = scissors();
    found.explain!.connections.crossover!.transits.dn_straight!.way = [
      ["bend_3", ""],
    ];
    found.explain!.connections.crossover!.transits.up_straight!.way = [
      ["bend_3", ""],
    ];
    expect(routes(through(found, "bend_3"))).toBe(false);
  });

  it("says nothing at all routes nothing", () => {
    expect(routes(through(scissors(), "yard_stop"))).toBe(false);
  });
});

describe("the pairs among the transits through a symbol", () => {
  it("splits them into those that run together and those that cannot", () => {
    expect(amongst(scissors(), "dn_e_points")).toEqual([
      {
        one: "dn_straight",
        two: "up_to_dn",
        concurrent: false,
        shared: ["dn_e_points"],
        legs: [["straight"], ["diverging"]],
      },
    ]);
  });

  it("names the symbol that blocks, which need not be the one selected", () => {
    // Both ways over the diamond also cross a turnout each, but what stops
    // them is the diamond itself: `shared` is the claim to check by looking.
    expect(amongst(scissors(), "diamond")).toEqual([
      {
        one: "dn_to_up",
        two: "up_to_dn",
        concurrent: false,
        shared: ["diamond"],
        legs: [["b"], ["a"]],
      },
    ]);
  });

  it("reports a pair that runs together, sharing the symbol harmlessly", () => {
    const found = scissors();
    const crossover = found.explain!.connections.crossover!;
    crossover.transits.dn_straight!.way = [["diamond", "a"]];
    crossover.transits.up_straight!.way = [["diamond", "b"]];
    const pairs = amongst(found, "diamond").filter(
      (pair) => pair.one === "dn_straight" && pair.two === "up_straight",
    );
    expect(pairs).toEqual([
      {
        one: "dn_straight",
        two: "up_straight",
        concurrent: true,
        shared: [],
        legs: [["a"], ["b"]],
      },
    ]);
  });
});

describe("names two connections cannot both wear", () => {
  it("finds nothing to say about a drawing that agrees with itself", () => {
    expect(clashes(scissors())).toEqual([]);
  });

  it("reports a name a split left on both halves, with each half's symbols", () => {
    const found = scissors();
    found.junctions = [
      { name: "airolo", names: ["airolo"], symbols: ["sw1", "sw2"] },
      { name: "airolo", names: ["airolo"], symbols: ["sw3"] },
    ];
    expect(clashes(found)).toEqual([
      {
        kind: "duplicate",
        names: ["airolo"],
        where: [
          ["sw1", "sw2"],
          ["sw3"],
        ],
      },
    ]);
  });

  it("reports a junction whose own symbols disagree about its name", () => {
    const found = scissors();
    found.junctions = [
      { name: null, names: ["airolo", "bodio"], symbols: ["sw1", "sw2"] },
    ];
    expect(clashes(found)).toEqual([
      {
        kind: "disagreement",
        names: ["airolo", "bodio"],
        where: [["sw1", "sw2"]],
      },
    ]);
  });

  it("names only the typed ones where a merge left minted names too", () => {
    const found = scissors();
    found.junctions = [
      { name: null, names: ["airolo", "bodio", "j4"], symbols: ["sw1", "sw2"] },
    ];
    expect(clashes(found)).toEqual([
      {
        kind: "disagreement",
        names: ["airolo", "bodio"],
        where: [["sw1", "sw2"]],
      },
    ]);
  });

  it("says nothing about the names a merge left that the editor is collapsing", () => {
    // Wiring junctions together leaves a minted name from each on one
    // junction. `settle` collapses them by the next review, so reporting it
    // shows a finding the editor is in the middle of fixing itself.
    const found = scissors();
    found.junctions = [
      { name: null, names: ["j2", "j5"], symbols: ["sw1", "sw2", "sw3"] },
    ];
    expect(clashes(found)).toEqual([]);
  });

  it("says nothing where a merge left one typed name among minted ones", () => {
    const found = scissors();
    found.junctions = [
      { name: null, names: ["airolo", "j5"], symbols: ["sw1", "sw2"] },
    ];
    expect(clashes(found)).toEqual([]);
  });

  it("says nothing about a duplicate the editor minted and is re-minting", () => {
    // `settle` re-mints a minted name a split left on both halves, so it is
    // gone by the next review. Reporting it in between shows a finding the
    // editor is in the middle of fixing itself.
    const found = scissors();
    found.junctions = [
      { name: "j7", names: ["j7"], symbols: ["sw1", "sw2"] },
      { name: "j7", names: ["j7"], symbols: ["sw3"] },
    ];
    expect(clashes(found)).toEqual([]);
  });

  it("reports a joint by its block ends, having no symbols to name", () => {
    const found = scissors();
    found.junctions = [
      { name: "airolo", names: ["airolo"], symbols: ["sw1"] },
    ];
    found.joints = [
      {
        ends: ["dn_e.B", "yard_e.A"],
        wires: [["dn_e.B", "yard_e.A"]],
        name: "airolo",
        names: ["airolo"],
      },
    ];
    expect(clashes(found)).toEqual([
      {
        kind: "duplicate",
        names: ["airolo"],
        where: [["sw1"], ["dn_e.B", "yard_e.A"]],
      },
    ]);
  });
});

describe("the block ends carrying no signal", () => {
  /** A siding: `yard` runs out of the scissors at its A end and into a buffer
   *  stop at its B end, which is Claro 4's shape. */
  function siding(): Review {
    const found = scissors();
    found.layout!.blocks = { dn_e: { length: 3200 }, yard: { length: 900 } };
    found.layout!.connections.throat = {
      transits: { into_yard: ["dn_e.B", "yard.A"] },
    };
    return found;
  }

  it("darkens an end no transit leaves", () => {
    expect(dark(siding()).get("yard")).toEqual(new Set(["B"]));
  });

  it("leaves an end a transit leaves alone", () => {
    expect(dark(siding()).get("yard")?.has("A")).toBe(false);
  });

  it("leaves an unwired end alone, it being unfinished rather than blind", () => {
    // A block dropped on the sheet is in no transit at either end. Both
    // signals vanishing there would read as a fault rather than as a siding.
    const found = siding();
    found.red_pins = ["yard.A", "yard.B"];
    expect(dark(found).get("yard")).toBeUndefined();
  });

  it("darkens nothing when the drawing does not derive", () => {
    // No layout is no answer, and no answer is not evidence of a dead end.
    const found = siding();
    found.layout = null;
    expect(dark(found).size).toBe(0);
  });

  it("counts a joint's ends as routed, a joint being a connection too", () => {
    const found = siding();
    found.layout!.connections.joint = {
      transits: { straight_through: ["yard.B", "dn_e.A"] },
    };
    expect(dark(found).get("yard")).toBeUndefined();
  });
});
