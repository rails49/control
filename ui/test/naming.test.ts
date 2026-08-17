import { describe, expect, it } from "vitest";

import { wireConnection, type Drawing } from "../src/model/drawing.js";
import { Editor } from "../src/model/editor.js";
import {
  minted,
  nameJoint,
  nameJunction,
  settle,
} from "../src/model/naming.js";
import type { Joint, Junction, Review } from "../src/model/store.js";

function review(parts: {
  junctions?: Junction[];
  joints?: Joint[];
}): Review {
  return {
    red_pins: [],
    junctions: parts.junctions ?? [],
    joints: parts.joints ?? [],
    layout: null,
    explain: null,
    refused: null,
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

  it("leaves a junction someone has named alone", () => {
    const drawing = throat();
    drawing.symbols.sw1!.connection = "airolo";
    drawing.symbols.sw2!.connection = "airolo";
    const found = review({
      junctions: [junction("airolo", ["airolo"], ["sw1", "sw2"])],
    });
    expect(settle(drawing, found)).toBe(false);
    expect(drawing.symbols.sw1!.connection).toBe("airolo");
  });

  it("leaves a junction two people have named differently to derivation", () => {
    // Choosing which half is Airolo is not the editor's decision to make, so
    // the refusal stands and the findings list says so.
    const drawing = throat();
    drawing.symbols.sw1!.connection = "airolo";
    drawing.symbols.sw2!.connection = "claro";
    const found = review({
      junctions: [junction(null, ["airolo", "claro"], ["sw1", "sw2"])],
    });
    expect(settle(drawing, found)).toBe(false);
    expect(drawing.symbols.sw1!.connection).toBe("airolo");
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

  it("leaves a typed name on both halves, for derivation to refuse", () => {
    const drawing = throat();
    for (const spec of Object.values(drawing.symbols)) spec.connection = "airolo";
    const found = review({
      junctions: [
        junction("airolo", ["airolo"], ["sw1", "sw2"]),
        junction("airolo", ["airolo"], ["x1"]),
      ],
    });
    expect(settle(drawing, found)).toBe(false);
    expect(drawing.symbols.x1!.connection).toBe("airolo");
  });
});

describe("a wire between two blocks", () => {
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

  it("takes a minted name on one segment of the chain", () => {
    // A person draws a wire between two blocks and is asked nothing.
    const drawing = joined();
    expect(settle(drawing, review({ joints: [chain] }))).toBe(true);
    const named = drawing.wires.map(wireConnection).filter(Boolean);
    expect(named).toEqual(["j1"]);
  });

  it("leaves a joint someone named where it is", () => {
    const drawing = joined();
    drawing.wires[0] = { pins: ["west.B", "n1.P"], connection: "gap" };
    const found = review({
      joints: [{ ...chain, name: "gap", names: ["gap"] }],
    });
    expect(settle(drawing, found)).toBe(false);
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
