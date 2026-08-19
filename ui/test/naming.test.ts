import { describe, expect, it } from "vitest";

import {
  wireConnection,
  wirePins,
  type Drawing,
} from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import {
  minted,
  nameJoint,
  nameJunction,
  remint,
  settle,
} from "../src/model/naming.js";
import type { Joint, Junction, Review } from "../src/model/store.js";

function review(parts: {
  junctions?: Junction[];
  joints?: Joint[];
}): Review {
  return {
    red_pins: [],
    unpaired_portals: [],
    junctions: parts.junctions ?? [],
    joints: parts.joints ?? [],
    layout: null,
    explain: null,
    refused: null,
    offending: [],
  };
}

function throat(): Drawing {
  return {
    drawing: "test",
    symbols: {
      sw1: { kind: "turnout", at: [0, 0] },
      sw2: { kind: "turnout", at: [4, 0] },
      x1: { kind: "crossing", at: [8, 0] },
    },
    wires: [],
  };
}

function junction(name: string | null, names: string[], symbols: string[]) {
  return { name, names, symbols };
}

describe("minting a junction's name", () => {
  it("names a junction nobody has named, on every one of its symbols", () => {
    const drawing = throat();
    expect(
      settle(drawing, review({ junctions: [junction(null, [], ["sw1", "sw2"])] })),
    ).toBe(true);
    expect(drawing.symbols.sw1!.connection).toBe("j1");
    expect(drawing.symbols.sw2!.connection).toBe("j1");
  });

  it("keeps out of the way of names already in use", () => {
    const drawing = throat();
    drawing.symbols.x1!.connection = "j1";
    const found = review({
      junctions: [
        junction("j1", ["j1"], ["x1"]),
        junction(null, [], ["sw1", "sw2"]),
      ],
    });
    settle(drawing, found);
    expect(drawing.symbols.sw1!.connection).toBe("j2");
  });

  it("settles in one pass: a second look writes nothing", () => {
    const drawing = throat();
    const found = review({ junctions: [junction(null, [], ["sw1", "sw2"])] });
    settle(drawing, found);
    const after = review({
      junctions: [junction("j1", ["j1"], ["sw1", "sw2"])],
    });
    expect(settle(drawing, after)).toBe(false);
  });
});

describe("a split or a merge", () => {
  it("re-mints a minted name silently on both halves", () => {
    // Nobody is reading `j1`, so both sides take a fresh one rather than the
    // editor guessing which half kept the identity.
    const drawing = throat();
    for (const spec of Object.values(drawing.symbols)) spec.connection = "j1";
    const found = review({
      junctions: [
        junction("j1", ["j1"], ["sw1", "sw2"]),
        junction("j1", ["j1"], ["x1"]),
      ],
    });
    expect(settle(drawing, found)).toBe(true);
    expect(drawing.symbols.sw1!.connection).toBe("j2");
    expect(drawing.symbols.x1!.connection).toBe("j3");
  });

  it("collapses the minted names a merge left onto the lowest of them", () => {
    // Wiring two junctions together leaves a name from each on one junction.
    // Nobody is reading either, so the lowest wins and the other comes off,
    // which is the smallest the diff can be.
    const drawing = throat();
    drawing.symbols.sw1!.connection = "j2";
    drawing.symbols.sw2!.connection = "j2";
    drawing.symbols.x1!.connection = "j5";
    const found = review({
      junctions: [junction(null, ["j2", "j5"], ["sw1", "sw2", "x1"])],
    });
    expect(settle(drawing, found)).toBe(true);
    expect(
      Object.values(drawing.symbols).map((spec) => spec.connection),
    ).toEqual(["j2", "j2", "j2"]);
  });

  it("compares minted names by number, not as text", () => {
    const drawing = throat();
    drawing.symbols.sw1!.connection = "j9";
    drawing.symbols.x1!.connection = "j10";
    const found = review({
      junctions: [junction(null, ["j10", "j9"], ["sw1", "x1"])],
    });
    settle(drawing, found);
    expect(drawing.symbols.sw1!.connection).toBe("j9");
  });

});

/** Two blocks joined by a bare wire through a bend: a joint, which is a
 *  connection in itself and carries its name on one of its own wires. */
const joined = (): Drawing => ({
  drawing: "test",
  symbols: {
    west: { kind: "block", length: 1000 },
    east: { kind: "block", length: 1000 },
    n1: { kind: "pin" },
  },
  wires: [
    ["west.B", "n1.P"],
    ["n1.P", "east.A"],
  ],
});

const chain: Joint = {
  ends: ["east.A", "west.B"],
  wires: [
    ["n1.P", "west.B"],
    ["east.A", "n1.P"],
  ],
  name: null,
  names: [],
};

describe("a wire between two blocks", () => {
  it("takes a minted name on one segment of the chain", () => {
    // A person draws a wire between two blocks and is asked nothing.
    const drawing = joined();
    expect(settle(drawing, review({ joints: [chain] }))).toBe(true);
    const named = drawing.wires.map(wireConnection).filter(Boolean);
    expect(named).toEqual(["j1"]);
  });

  it("renaming leaves one segment of the chain carrying the name", () => {
    // Two names on one joint are refused, so a rename cannot add a second: it
    // writes the new name on one segment and takes the old off the rest.
    const drawing = joined();
    drawing.wires = [
      { pins: ["west.B", "n1.P"], connection: "j1" },
      { pins: ["n1.P", "east.A"], connection: "j1" },
    ];
    nameJoint(drawing, chain, "gap");
    expect(drawing.wires.map(wireConnection)).toEqual(["gap", undefined]);
  });
});

/**
 * Opening a drawing re-mints every connection name it carries (ADR-0023).
 *
 * A typed connection name is a name derivation can refuse and the editor
 * cannot settle: delete the block between two named junctions, wire the
 * neighbours together, and the two names are one connection's. No open drawing
 * holds one, so that state cannot arise — the drawing as opened is the drawing
 * as loaded, with the names replaced.
 */
describe("opening a drawing", () => {
  it("replaces a name a person typed with one of its own", () => {
    const drawing = throat();
    drawing.symbols.sw1!.connection = "airolo";
    drawing.symbols.sw2!.connection = "airolo";
    const found = review({
      junctions: [junction("airolo", ["airolo"], ["sw1", "sw2"])],
    });
    expect(remint(drawing, found)).toBe(true);
    expect(drawing.symbols.sw1!.connection).toBe("j1");
  });

  it("leaves every member of the junction wearing the one name", () => {
    const drawing = throat();
    drawing.symbols.sw1!.connection = "airolo";
    drawing.symbols.sw2!.connection = "airolo";
    drawing.symbols.x1!.connection = "airolo";
    const found = review({
      junctions: [junction("airolo", ["airolo"], ["sw1", "sw2", "x1"])],
    });
    remint(drawing, found);
    expect(
      Object.values(drawing.symbols).map((spec) => spec.connection),
    ).toEqual(["j1", "j1", "j1"]);
  });

  it("replaces a joint's typed name the same way", () => {
    // A bare wire between two blocks is a connection too, and no more a
    // special case here than it is anywhere else.
    const drawing = joined();
    drawing.wires[0] = { pins: ["west.B", "n1.P"], connection: "gap" };
    const found = review({
      joints: [{ ...chain, name: "gap", names: ["gap"] }],
    });
    expect(remint(drawing, found)).toBe(true);
    expect(drawing.wires.map(wireConnection).filter(Boolean)).toEqual(["j1"]);
  });

  it("leaves a name it minted itself alone", () => {
    const drawing = throat();
    drawing.symbols.sw1!.connection = "j1";
    drawing.symbols.sw2!.connection = "j1";
    const found = review({
      junctions: [junction("j1", ["j1"], ["sw1", "sw2"])],
    });
    expect(remint(drawing, found)).toBe(false);
    expect(drawing.symbols.sw1!.connection).toBe("j1");
  });

  it("keeps out of the way of the minted names it is keeping", () => {
    const drawing = throat();
    drawing.symbols.x1!.connection = "j1";
    drawing.symbols.sw1!.connection = "airolo";
    drawing.symbols.sw2!.connection = "airolo";
    const found = review({
      junctions: [
        junction("j1", ["j1"], ["x1"]),
        junction("airolo", ["airolo"], ["sw1", "sw2"]),
      ],
    });
    remint(drawing, found);
    expect(drawing.symbols.x1!.connection).toBe("j1");
    expect(drawing.symbols.sw1!.connection).toBe("j2");
  });

  it("settles a merge of two junctions a person had named", () => {
    // The case the editor could not settle: delete the block between Airolo
    // and Claro West and wire the neighbours together, and derivation refused
    // because choosing which half is Airolo was nobody's to make. With neither
    // name honoured there is nothing to choose.
    const drawing = throat();
    drawing.symbols.sw1!.connection = "airolo";
    drawing.symbols.sw2!.connection = "airolo";
    drawing.symbols.x1!.connection = "claro_west";
    const found = review({
      junctions: [junction(null, ["airolo", "claro_west"], ["sw1", "sw2", "x1"])],
    });
    expect(remint(drawing, found)).toBe(true);
    expect(
      Object.values(drawing.symbols).map((spec) => spec.connection),
    ).toEqual(["j1", "j1", "j1"]);
  });

  it("re-mints both halves of a split a typed name was left on", () => {
    const drawing = throat();
    for (const spec of Object.values(drawing.symbols)) spec.connection = "airolo";
    const found = review({
      junctions: [
        junction("airolo", ["airolo"], ["sw1", "sw2"]),
        junction("airolo", ["airolo"], ["x1"]),
      ],
    });
    expect(remint(drawing, found)).toBe(true);
    expect(drawing.symbols.sw1!.connection).toBe("j1");
    expect(drawing.symbols.x1!.connection).toBe("j2");
  });

  /** A junction of one symbol is named after that symbol and writes no
   *  `connection` at all, so there is no typed name to replace and the drawing
   *  opens as it was written. */
  it("writes nothing onto a lone symbol that names its own connection", () => {
    const drawing = throat();
    const found = review({
      junctions: [junction("sw1", [], ["sw1"])],
    });
    expect(remint(drawing, found)).toBe(false);
    expect(drawing.symbols.sw1).not.toHaveProperty("connection");
  });

  it("touches nothing but the names, so the topology is what it was", () => {
    const drawing = throat();
    drawing.symbols.sw1!.connection = "airolo";
    drawing.symbols.sw2!.connection = "airolo";
    const before = structuredClone(drawing);
    remint(
      drawing,
      review({ junctions: [junction("airolo", ["airolo"], ["sw1", "sw2"])] }),
    );
    expect(bare(drawing)).toEqual(bare(before));
  });

  /** The drawing with every connection name taken off it: what a re-mint is
   *  not allowed to change. */
  function bare(drawing: Drawing): Drawing {
    const stripped = structuredClone(drawing);
    for (const spec of Object.values(stripped.symbols)) delete spec.connection;
    stripped.wires = stripped.wires.map(wirePins);
    return stripped;
  }
});

describe("a review that arrived too late", () => {
  it("is not written onto a drawing that has moved on", () => {
    // A review is a round trip and an edit can land while it is in flight.
    // Naming junctions that are no longer there would leave a `connection` on
    // symbols that no longer form one, which derivation then refuses.
    const editor = new Editor(throat());
    const found = review({ junctions: [junction(null, [], ["sw1", "sw2"])] });
    const stale = editor.revision;
    editor.select(["x1"]);
    editor.move(4, 0);
    expect(editor.settle(found, stale)).toBe(false);
    expect(editor.drawing.symbols.sw1!.connection).toBeUndefined();
    expect(editor.settle(found, editor.revision)).toBe(true);
  });
});

describe("telling a minted name from a typed one", () => {
  it("knows the ones it makes", () => {
    expect(minted("j1")).toBe(true);
    expect(minted("j17")).toBe(true);
    expect(minted("airolo")).toBe(false);
    expect(minted("j")).toBe(false);
    expect(minted("j0")).toBe(false);
    expect(minted("junction3")).toBe(false);
  });
});

describe("naming a junction by hand", () => {
  it("writes the name onto every symbol of the region", () => {
    const drawing = throat();
    nameJunction(drawing, ["sw1", "sw2", "x1"], "airolo");
    expect(
      Object.values(drawing.symbols).map((spec) => spec.connection),
    ).toEqual(["airolo", "airolo", "airolo"]);
  });
});

/** A bend joining a wire to a turnout is in the junction's symbols, because a
 *  junction is the connected group of non-block symbols. It declares no
 *  transit, and the drawing schema gives a joiner no `connection`: writing one
 *  refused the whole document. */
describe("a junction with a joiner in it", () => {
  function bent(): Drawing {
    return {
      drawing: "test",
      symbols: {
        sw1: { kind: "turnout", at: [0, 0] },
        n1: { kind: "pin", at: [4, 0] },
        e1: { kind: "terminal", at: [6, 0] },
        p1: { kind: "portal", at: [8, 0], label: "p1" },
      },
      wires: [],
    };
  }

  it("names the symbols that declare a transit and no others", () => {
    const drawing = bent();
    nameJunction(drawing, ["sw1", "n1", "e1", "p1"], "airolo");
    expect(drawing.symbols.sw1!.connection).toBe("airolo");
    expect(drawing.symbols.n1).not.toHaveProperty("connection");
    expect(drawing.symbols.e1).not.toHaveProperty("connection");
    expect(drawing.symbols.p1).not.toHaveProperty("connection");
  });

  it("mints the same way, leaving the joiner clean", () => {
    const drawing = bent();
    expect(
      settle(drawing, review({ junctions: [junction(null, [], ["sw1", "n1"])] })),
    ).toBe(true);
    expect(drawing.symbols.sw1!.connection).toBe("j1");
    expect(drawing.symbols.n1).not.toHaveProperty("connection");
  });

  it("takes back the one an older editor wrote", () => {
    const drawing = bent();
    drawing.symbols.n1!.connection = "airolo";
    nameJunction(drawing, ["sw1", "n1"], "airolo");
    expect(drawing.symbols.n1).not.toHaveProperty("connection");
  });
});
