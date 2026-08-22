/**
 * The drag gesture on the live panel (#72), tested the way the editor's
 * gesture model is: grid points in, an arrival-end set or a cancel out. No
 * DOM — the component converts pixels into squares and nothing else.
 */

import { describe, expect, it } from "vitest";

import {
  Drag,
  schedulingMachine,
  trainAt,
  type Drop,
  type Painted,
} from "../src/model/drag.js";
import type { Drawing } from "../src/model/drawing.js";
import type { BlockView } from "../src/model/panel.js";
import type { Review } from "../src/model/store.js";

/**
 * Two blocks side by side, each six squares long with A at its west end:
 * `a` spans x 0…6 on row 0, `b` spans x 0…6 on row 2.
 */
const DRAWING: Drawing = {
  drawing: "toy",
  symbols: {
    a: { kind: "block", at: [0, 0], length: 1000 },
    b: { kind: "block", at: [0, 2], length: 1000 },
  },
  wires: [],
};

const REVIEW: Review = {
  red_pins: [],
  unpaired_portals: [],
  junctions: [],
  joints: [],
  motor_faults: [],
  layout: null,
  explain: null,
  refused: null,
  offending: [],
};

const BLOCKS = new Map<string, BlockView>([
  ["a", { state: "occupied", train: "t1", toward: "B" }],
  ["b", { state: "free" }],
]);

/** A point inside block `b`, `along` of the way from its A end to its B end. */
function on(block: "a" | "b", along: number) {
  return { x: along * 6, y: block === "a" ? 0.5 : 2.5 };
}

function held(): Drag {
  const drag = new Drag();
  expect(drag.down(DRAWING, REVIEW, BLOCKS, on("a", 0.5))).toBe(true);
  return drag;
}

describe("taking hold", () => {
  it("takes hold of the train standing under the press", () => {
    const drag = held();
    expect(drag.train).toBe("t1");
  });

  it("ignores a press on a block with no train in it", () => {
    const drag = new Drag();
    expect(drag.down(DRAWING, REVIEW, BLOCKS, on("b", 0.5))).toBe(false);
    expect(drag.train).toBeNull();
  });

  it("ignores a press on bare paper", () => {
    const drag = new Drag();
    expect(drag.down(DRAWING, REVIEW, BLOCKS, { x: 20, y: 20 })).toBe(false);
  });
});

/**
 * The one question the press and the right-click share (#124): which train
 * was clicked. Asked once so the drag and the "Turn around" menu can never
 * disagree about it.
 */
describe("the train under a point", () => {
  const asked = (point: { x: number; y: number }) =>
    trainAt(DRAWING, REVIEW, BLOCKS, point);

  it("names the train and the block it stands in", () => {
    expect(asked(on("a", 0.5))).toEqual({ train: "t1", block: "a" });
  });

  it("names none over an empty block or over bare paper", () => {
    expect(asked(on("b", 0.5))).toBeNull();
    expect(asked({ x: 20, y: 20 })).toBeNull();
  });

  /** A block locked ahead of a train is not a train standing:
   *  the arrow it would turn belongs to a block somewhere else. */
  it("names none over a block merely locked or planned", () => {
    const ahead = new Map<string, BlockView>([
      ["a", { state: "locked", train: "t1" }],
      ["b", { state: "planned", train: "t1" }],
    ]);
    expect(trainAt(DRAWING, REVIEW, ahead, on("a", 0.5))).toBeNull();
    expect(trainAt(DRAWING, REVIEW, ahead, on("b", 0.5))).toBeNull();
  });
});

describe("the thirds rule", () => {
  it("names the end the train enters through, dropping on an outer third", () => {
    const drag = held();
    drag.moved(DRAWING, REVIEW, on("b", 0.1));
    expect(drag.drop?.dest).toEqual(["b.A"]);
    drag.moved(DRAWING, REVIEW, on("b", 0.9));
    expect(drag.drop?.dest).toEqual(["b.B"]);
  });

  it("names both ends — either way round — on the middle third", () => {
    const drag = held();
    drag.moved(DRAWING, REVIEW, on("b", 0.5));
    expect(drag.drop).toEqual({ train: "t1", block: "b", dest: ["b.A", "b.B"] });
  });

  it("splits the block at the thirds, whichever way it is drawn", () => {
    const turned: Drawing = {
      ...DRAWING,
      symbols: { ...DRAWING.symbols, b: { kind: "block", at: [3, 2], rot: 90 } },
    };
    const drag = new Drag();
    drag.down(turned, REVIEW, BLOCKS, on("a", 0.5));
    // Turned a quarter, `b` runs south from (3.5, 2) to (3.5, 8): A on top.
    drag.moved(turned, REVIEW, { x: 3.5, y: 2.5 });
    expect(drag.drop?.dest).toEqual(["b.A"]);
    drag.moved(turned, REVIEW, { x: 3.5, y: 7.5 });
    expect(drag.drop?.dest).toEqual(["b.B"]);
    drag.moved(turned, REVIEW, { x: 3.5, y: 5 });
    expect(drag.drop?.dest).toEqual(["b.A", "b.B"]);
  });

  it("reads the ends of a flipped block from its pins, not from the page", () => {
    const flipped: Drawing = {
      ...DRAWING,
      symbols: { ...DRAWING.symbols, b: { kind: "block", at: [0, 2], flip: true } },
    };
    const drag = new Drag();
    drag.down(flipped, REVIEW, BLOCKS, on("a", 0.5));
    drag.moved(flipped, REVIEW, on("b", 0.1));
    expect(drag.drop?.dest).toEqual(["b.B"]);
  });
});

describe("dropping", () => {
  it("hands back what the hover showed", () => {
    const drag = held();
    drag.moved(DRAWING, REVIEW, on("b", 0.9));
    expect(drag.up(DRAWING, REVIEW, on("b", 0.9))).toEqual({
      train: "t1",
      block: "b",
      dest: ["b.B"],
    });
  });

  it("cancels on the train's own block, wherever in it", () => {
    const drag = held();
    drag.moved(DRAWING, REVIEW, on("a", 0.1));
    expect(drag.drop).toBeNull();
    expect(drag.up(DRAWING, REVIEW, on("a", 0.1))).toBeNull();
  });

  it("cancels on bare paper", () => {
    const drag = held();
    expect(drag.up(DRAWING, REVIEW, { x: 20, y: 20 })).toBeNull();
  });

  it("cancels when nothing was taken hold of", () => {
    const drag = new Drag();
    expect(drag.up(DRAWING, REVIEW, on("b", 0.5))).toBeNull();
  });

  it("lets go, so the next press starts a drag of its own", () => {
    const drag = held();
    drag.up(DRAWING, REVIEW, on("b", 0.5));
    expect(drag.train).toBeNull();
    expect(drag.drop).toBeNull();
  });

  it("submits a drop on an occupied block: the dispatcher decides, not this", () => {
    const busy = new Map(BLOCKS).set("b", {
      state: "occupied",
      train: "t2",
    } as BlockView);
    const drag = new Drag();
    drag.down(DRAWING, REVIEW, busy, on("a", 0.5));
    expect(drag.up(DRAWING, REVIEW, on("b", 0.5))?.dest).toEqual([
      "b.A",
      "b.B",
    ]);
  });
});

describe("what the drag draws", () => {
  it("runs from where the press was to where the pointer is", () => {
    const drag = held();
    drag.moved(DRAWING, REVIEW, on("b", 0.9));
    expect(drag.from).toEqual(on("a", 0.5));
    expect(drag.to).toEqual(on("b", 0.9));
  });

  it("abandons the gesture when the pointer leaves", () => {
    const drag = held();
    drag.cancel();
    expect(drag.train).toBeNull();
    expect(drag.from).toBeNull();
  });
});

/**
 * The same rules driven the way the canvas drives them (#168): one call per
 * pointer event, an `Outcome` back, and the gesture in flight as marks in grid
 * squares. `Drag` answers the same `Machine` the editor's `Gesture` does, so
 * the surface asks one question of both and this is the run view's half of it.
 */
describe("the run view's machine", () => {
  const PAINTED: Painted = {
    drawing: DRAWING,
    review: REVIEW,
    blocks: BLOCKS,
  };

  /** A machine over the drawing above, with the drops it submitted. */
  function machine(painting: Painted | null = PAINTED) {
    const sent: Drop[] = [];
    const it = schedulingMachine(new Drag(), () => painting, (drop) => {
      sent.push(drop);
    });
    return { sent, it };
  }

  const press = { button: 0, shift: false, screen: { x: 0, y: 0 } };

  it("is quiet through and through with nothing to gesture at", () => {
    // No railroad on screen, or no session to submit to: every call answers
    // quiet and nothing is drawn or written. That is the whole of the gate.
    const { sent, it } = machine(null);
    expect(it.down(on("a", 0.5), press)).toBe("quiet");
    expect(it.moved(on("b", 0.5), { x: 0, y: 0 })).toBe("quiet");
    expect(it.up(on("b", 0.5))).toBe("quiet");
    expect(it.left()).toBe("quiet");
    expect(it.marks).toBeNull();
    expect(it.menu(on("a", 0.5)).found).toBeNull();
    expect(sent).toEqual([]);
  });

  it("draws the reach and the ends a drop would ask for", () => {
    const { it } = machine();
    expect(it.down(on("a", 0.5), press)).toBe("render");
    expect(it.marks).toEqual({ reach: { from: on("a", 0.5), to: on("a", 0.5) } });

    it.moved(on("b", 0.9), { x: 0, y: 0 });
    // The outer third asks for one end, and the mark is where that end sits.
    expect(it.marks).toEqual({
      reach: { from: on("a", 0.5), to: on("b", 0.9) },
      target: { block: "b", ends: [{ x: 6, y: 2.5 }] },
    });
  });

  it("submits the drop, and nothing where the release cancels", () => {
    const { sent, it } = machine();
    it.down(on("a", 0.5), press);
    expect(it.up(on("b", 0.5))).toBe("render");
    expect(sent).toEqual([{ train: "t1", block: "b", dest: ["b.A", "b.B"] }]);
    expect(it.marks).toBeNull();

    it.down(on("a", 0.5), press);
    it.up(on("a", 0.1));
    expect(sent).toHaveLength(1);
  });

  /** The pointer left the sheet, or the gesture under it was cancelled. */
  it("abandons a drag in flight and nothing otherwise", () => {
    const { sent, it } = machine();
    it.down(on("a", 0.5), press);
    expect(it.left()).toBe("render");
    expect(it.marks).toBeNull();
    expect(sent).toEqual([]);
    expect(it.left()).toBe("quiet");
  });

  /** The right-click asks the same question of the same point the press does,
   *  and takes the gesture over from a drag the press had started. */
  it("finds the train under a right-click, abandoning any drag", () => {
    const { it } = machine();
    it.down(on("a", 0.5), press);
    expect(it.menu(on("a", 0.5))).toEqual({
      outcome: "render",
      found: { train: "t1", block: "a" },
    });
    expect(it.marks).toBeNull();
    expect(it.menu(on("b", 0.5)).found).toBeNull();
  });

  /** Nothing on a run's sheet is drawn out of place: a train's marker moves
   *  with the pointer and the drawing under it does not. */
  it("shifts no symbol", () => {
    const { it } = machine();
    it.down(on("a", 0.5), press);
    it.moved(on("b", 0.5), { x: 0, y: 0 });
    expect(it.shift("a")).toEqual({ x: 0, y: 0 });
  });
});
