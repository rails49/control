import { describe, expect, it } from "vitest";

import {
  WHOLE,
  against,
  amongst,
  chosenWay,
  dark,
  lit,
  litLast,
  litWires,
  routes,
  through,
  unpaired,
  wiresOn,
} from "../src/model/inspect.js";
import { wirePins, type Wire } from "../src/model/drawing.js";
import type { Review, Transit } from "../src/model/store.js";

/**
 * `crossover-yard`'s scissors, as `/review` answers it. Four transits over
 * four turnouts and a diamond, with one concurrent pair: the two straights.
 * It is the derivation DRAWING.md leans on hardest, and small enough to read.
 */
function scissors(): Review {
  return {
    red_pins: [],
    unpaired_portals: [],
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
    motor_faults: [],
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
    offending: [],
  };
}

describe("the way a chosen transit takes", () => {
  it("lights each symbol on the way at the leg the way takes", () => {
    const way = lit(
      chosenWay(scissors(), { connection: "crossover", transit: "up_to_dn" }),
    );
    expect(way.get("dn_e_points")).toEqual(new Set(["diverging"]));
    expect(way.get("diamond")).toEqual(new Set(["a"]));
    expect(way.get("up_w_points")).toEqual(new Set(["diverging"]));
  });

  it("lights the two block ends the transit runs between, whole", () => {
    const way = lit(
      chosenWay(scissors(), { connection: "crossover", transit: "up_to_dn" }),
    );
    expect(way.get("dn_e")).toEqual(new Set([WHOLE]));
    expect(way.get("up_w")).toEqual(new Set([WHOLE]));
  });

  it("lights a joiner whole, having no leg of its own to light", () => {
    const found = scissors();
    found.explain!.connections.crossover!.transits.dn_straight!.way = [
      ["bend_3", ""],
      ["dn_w_points", "straight"],
    ];
    const way = lit(
      chosenWay(found, { connection: "crossover", transit: "dn_straight" }),
    );
    expect(way.get("bend_3")).toEqual(new Set([WHOLE]));
  });

  it("lights nothing when nothing is chosen, or when the choice is stale", () => {
    expect(lit(chosenWay(scissors(), null)).size).toBe(0);
    expect(
      lit(chosenWay(scissors(), { connection: "crossover", transit: "gone" }))
        .size,
    ).toBe(0);
  });
});

/**
 * The wires a way is drawn over: the store's own rule, transcribed
 * (store/drawing.py `wires_on`, proven exact there against every railroad).
 *
 * Four shapes, because the drawing decides which one a way is: a junction
 * with wires inside it, a joint that is one bare wire, a joint routed round a
 * corner through bend pins, and a joint crossing the canvas through a portal
 * pair. The last is the one with a join that is not a wire.
 */
describe("the wires a way is drawn over", () => {
  const wires: Wire[] = [
    ["a.B", "sw1.toe"],
    ["sw1.straight", "b.A"],
    ["sw1.diverging", "bend.P"],
    ["bend.P", "c.A"],
    { pins: ["b.B", "c.B"], connection: "jt" },
    ["d.A", "here.P"],
    ["there.P", "e.B"],
    ["f.A", "g.B"],
  ];
  const key = (one: string, two: string) => [one, two].sort().join(" ");

  it("takes a wire when both its pins are the way's ends or on its symbols", () => {
    const way: Transit = { ends: ["a.B", "b.A"], way: [["sw1", "straight"]] };
    expect(wiresOn(way, wires)).toEqual([
      key("a.B", "sw1.toe"),
      key("sw1.straight", "b.A"),
    ]);
  });

  it("takes the wires inside a junction, between the symbols the way crosses", () => {
    const way: Transit = {
      ends: ["a.B", "c.A"],
      way: [
        ["sw1", "diverging"],
        ["bend", ""],
      ],
    };
    expect(wiresOn(way, wires)).toEqual([
      key("a.B", "sw1.toe"),
      key("sw1.diverging", "bend.P"),
      key("bend.P", "c.A"),
    ]);
  });

  it("takes the one wire a joint is, which crosses no symbol at all", () => {
    // The case that lights nothing today: no symbol on the way means no leg
    // to light, so a plain wired connection was dark between its two blocks.
    const way: Transit = { ends: ["b.B", "c.B"], way: [] };
    expect(wiresOn(way, wires)).toEqual([key("b.B", "c.B")]);
  });

  it("takes both sides of a portal pair, the pairing itself being no wire", () => {
    const way: Transit = {
      ends: ["d.A", "e.B"],
      way: [
        ["here", ""],
        ["there", ""],
      ],
    };
    expect(wiresOn(way, wires)).toEqual([key("d.A", "here.P"), key("there.P", "e.B")]);
  });

  it("leaves the rest of the drawing dark", () => {
    const way: Transit = { ends: ["b.B", "c.B"], way: [] };
    expect(wiresOn(way, wires)).not.toContain(key("f.A", "g.B"));
  });

  it("unions the answers of several ways, never the ways themselves", () => {
    const ways: Transit[] = [
      { ends: ["a.B", "b.A"], way: [["sw1", "straight"]] },
      { ends: ["b.B", "c.B"], way: [] },
    ];
    expect(litWires(ways, wires)).toEqual(
      new Set([key("a.B", "sw1.toe"), key("sw1.straight", "b.A"), key("b.B", "c.B")]),
    );
  });

  it("lights nothing for no ways at all", () => {
    expect(litWires([], wires).size).toBe(0);
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

describe("the portals wearing a label that does not pair", () => {
  it("names each portal with the label it wears", () => {
    const found = scissors();
    found.unpaired_portals = [
      { label: "p1", portals: ["portal1"] },
      { label: "p2", portals: ["portal4"] },
    ];
    expect(unpaired(found)).toEqual(
      new Map([
        ["portal1", "p1"],
        ["portal4", "p2"],
      ]),
    );
  });

  it("names every portal wearing a label worn three times", () => {
    // Three is as unpaired as one, and the label is on all three: none of
    // them is the odd one out, so the mark cannot pick one.
    const found = scissors();
    found.unpaired_portals = [
      { label: "p1", portals: ["portal1", "portal2", "portal3"] },
    ];
    expect([...unpaired(found).keys()]).toEqual([
      "portal1",
      "portal2",
      "portal3",
    ]);
  });

  it("names nothing where every label pairs", () => {
    expect(unpaired(scissors()).size).toBe(0);
  });
});

/**
 * The order the wires are emitted in (#155).
 *
 * Two pages draw a drawing's wires — the editor's canvas and the panel — and
 * both need the lit ones last. What "lit" means differs between them, so the
 * rule takes a predicate; that it is one rule is what this suite pins.
 */
describe("the order a drawing's wires are drawn in", () => {
  const wires: Wire[] = [
    ["a.B", "sw1.toe"],
    ["sw1.straight", "b.A"],
    ["sw1.diverging", "c.A"],
    { pins: ["b.B", "c.B"], connection: "jt" },
  ];

  it("emits the lit wires after the unlit ones", () => {
    const alight = (wire: Wire) => wirePins(wire)[0] === "a.B";
    expect(litLast(wires, alight)).toEqual([
      wires[1],
      wires[2],
      wires[3],
      wires[0],
    ]);
  });

  it("keeps the drawing's own order within each of the two", () => {
    const alight = (wire: Wire) => wirePins(wire)[0]!.startsWith("sw1");
    expect(litLast(wires, alight)).toEqual([
      wires[0],
      wires[3],
      wires[1],
      wires[2],
    ]);
  });

  it("leaves the wires the caller gave it alone", () => {
    // With a predicate that reorders: a rule that sorted in place would pass
    // against one that lights everything, every comparison there being a tie.
    const given = [...wires];
    litLast(given, (wire) => wirePins(wire)[0] === "a.B");
    expect(given).toEqual(wires);
  });
});
