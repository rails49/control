// @vitest-environment happy-dom

/**
 * A railroad named and not built (#885): the layout interface comes up on a
 * railroad whose drawing is not a valid drawing, names it on
 * `tc49/layout/state/railroad` with `built: false`, and the page holds that
 * railroad's drawing and opens it in the Edit view, so it can be fixed
 * ([ADR-0085](../../docs/adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
 * decision 4). A row naming none, `""`, still closes it.
 *
 * A DOM test because it crosses the session, the loaded railroad and the
 * app's choice of view.
 */

import type { LookView } from "@rails49/look";
import { press } from "@rails49/look/testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcCanvas } from "../src/ui/tc-canvas.js";
import type { Drawing } from "../src/model/drawing.js";
import { centreOf } from "../src/model/geometry.js";
import {
  CLEAN,
  mounted,
  power,
  rail,
  running,
  serving,
  session,
  settled,
  shows,
  surface,
} from "./support/shell.js";
import {
  Broker,
  brokering,
  DERIVES,
  MIDDLE,
  RAILROAD,
  said,
  STOCK,
  stored,
  unbrokered,
  written,
} from "./support/session.js";

const POWER = "tc49/layout/state/power";
const POWER_WANTED = "tc49/layout/power_wanted";

beforeEach(() => {
  brokering();
  serving({
    drawings: ["toy"],
    rosterOf: () => STOCK,
    read: stored,
    review: () => Promise.resolve({ ...CLEAN, refused: "pin 'b1.a' is not wired" }),
  });
});

afterEach(unbrokered);

/** The view that is current, by the rail's mark. */
function current(shell: TcApp): string {
  return rail(shell).querySelector<LookView>("look-view[current]")!.name;
}

/** The drawing the editor holds, `""` for none. */
function opened(shell: TcApp): string {
  return session(shell).drawing.drawing;
}

/** A page on the run view whose broker comes up retaining `row`, as after a
 *  restart of the box. */
async function restarted(row: Record<string, unknown>): Promise<TcApp> {
  const shell = await mounted("run");
  Broker.last!.retains(POWER, { power: "off" });
  Broker.last!.retains(RAILROAD, row);
  Broker.last!.opens();
  await settled(shell);
  return shell;
}

describe("a railroad named with built: false", () => {
  it("holds its drawing and opens it in the Edit view", async () => {
    const shell = await restarted({ name: "toy", at: 5, built: false });

    expect(opened(shell)).toBe("toy");
    expect(current(shell)).toBe("edit");
  });

  it("is closed by a row naming none, as before", async () => {
    const shell = await restarted({ name: "toy", at: 5, built: false });

    await said(shell, RAILROAD, { name: "" });

    expect(opened(shell)).toBe("");
  });

  it("leaves a built railroad on the view the page was on", async () => {
    const shell = await restarted({ name: "toy", at: 5, built: true });

    expect(opened(shell)).toBe("toy");
    expect(current(shell)).toBe("run");
  });

  it("opens the Edit view once, not on every row saying so again", async () => {
    const shell = await restarted({ name: "toy", at: 5, built: false });
    await shows(shell, "stock");

    await said(shell, RAILROAD, { name: "toy", at: 6, built: false });

    expect(current(shell)).toBe("stock");
  });

  it("opens the Edit view when a build turns out to have built nothing", async () => {
    const shell = await restarted({ name: "toy", at: 5, built: true });

    await said(shell, RAILROAD, { name: "toy", at: 6, built: false });

    expect(current(shell)).toBe("edit");
  });
});

/**
 * A railroad that turns `built: false` while track power is on (#906): the
 * Edit view is shut then, so the page owes the open and pays it the first time
 * power reads `off`, if the same railroad is still not built (ADR-0085,
 * decisions 3 and 4).
 */
describe("a railroad turning built: false with power on", () => {
  /** A page on the run view on a built toy with track power on. */
  async function powered(): Promise<TcApp> {
    const shell = await mounted("run");
    Broker.last!.retains(POWER, { power: "on" });
    Broker.last!.retains(RAILROAD, { name: "toy", at: 5, built: true });
    Broker.last!.opens();
    await settled(shell);
    return shell;
  }

  it("opens the Edit view once power reads off", async () => {
    const shell = await powered();

    await said(shell, RAILROAD, { name: "toy", at: 6, built: false });
    expect(current(shell)).toBe("run");

    await said(shell, POWER, { power: "off" });
    expect(current(shell)).toBe("edit");
  });

  it("opens nothing where the railroad is built again before power is off", async () => {
    const shell = await powered();

    await said(shell, RAILROAD, { name: "toy", at: 6, built: false });
    await said(shell, RAILROAD, { name: "toy", at: 7, built: true });
    await said(shell, POWER, { power: "off" });

    expect(current(shell)).toBe("run");
  });

  it("opens nothing where another railroad is named before power is off", async () => {
    const shell = await powered();

    await said(shell, RAILROAD, { name: "toy", at: 6, built: false });
    await said(shell, RAILROAD, { name: "other", at: 7, built: false });
    await said(shell, POWER, { power: "off" });

    expect(current(shell)).toBe("run");
  });
});

/**
 * The run while the loaded railroad reads `built: false` (#886): the apps
 * built nothing from its saved drawing, so ON waits for the drawing to be
 * fixed, and the Run view draws it grey with no trains and no gestures
 * (ADR-0085, decision 4).
 *
 * The page's own review of the drawing is valid here, as where the store
 * refused the roster rather than the drawing: what the row says is what
 * holds, and the page has a panel model it could otherwise paint from.
 */
describe("a run on a railroad not built", () => {
  /** The toy drawing with a point a click would throw. */
  const POINTED: Drawing = {
    ...stored("toy"),
    symbols: { ...stored("toy").symbols, sw: { kind: "turnout", at: [10, 4], addr: "7" } },
  };
  const SWITCH = centreOf(POINTED.symbols.sw!);

  beforeEach(() => {
    serving({
      drawings: ["toy"],
      rosterOf: () => STOCK,
      read: () => structuredClone(POINTED),
      review: () => Promise.resolve(DERIVES),
    });
  });

  /** A page on the run view, the row saying `built`, with track power off
   *  and goods standing in a. */
  async function standing(built: boolean): Promise<TcApp> {
    const shell = await restarted({ name: "toy", at: 5, built });
    await shows(shell, "run");
    await said(shell, "tc49/dispatch/state/allocation", {
      trains: { goods: "a" },
      locks: { a: "goods" },
      requests: [],
    });
    return shell;
  }

  /** What is drawn on the run view's canvas. */
  function sheet(shell: TcApp): TcCanvas {
    return running(shell).renderRoot.querySelector<TcCanvas>("tc-canvas")!;
  }

  /** The canvas pressed and let go at each point in turn, as a mouse. A drag
   *  goes by way of a point further off than a click's slop, the two blocks'
   *  middles being closer than it: a release within it is a tap (#1018). */
  async function dragged(shell: TcApp, from: { x: number; y: number }, to = from) {
    const away = to === from ? [] : [["pointermove", { x: to.x, y: to.y + 10 }] as const];
    for (const [name, at] of [
      ["pointerdown", from] as const,
      ...away,
      ["pointermove", to] as const,
      ["pointerup", to] as const,
    ]) {
      surface(shell).dispatchEvent(
        new PointerEvent(name, { bubbles: true, button: 0, clientX: at.x, clientY: at.y }),
      );
    }
    await settled(shell);
  }

  it("refuses ON with Fix the drawing first and asks for nothing", async () => {
    const shell = await standing(false);

    expect(power(shell).toggleReason).toBe("Fix the drawing first");
    press(power(shell), "toggle");
    await settled(shell);

    expect(written()).not.toContainEqual(expect.objectContaining({ topic: POWER_WANTED }));
  });

  it("draws the drawing grey, with no trains", async () => {
    const shell = await standing(false);

    expect(sheet(shell).classList.contains("unbuilt")).toBe(true);
    expect(sheet(shell).renderRoot.querySelector("g[data-symbol] > title")).toBeNull();
  });

  it("throws nothing on a press, and asks for no request on a drag", async () => {
    const shell = await standing(false);

    await dragged(shell, SWITCH);
    await dragged(shell, MIDDLE.a, MIDDLE.b);

    expect(written()).toEqual([]);
  });

  /** The same page with the railroad built, so the two above are about
   *  `built` and not about the fixture. */
  it("paints the train and throws the point once it is built", async () => {
    const shell = await standing(true);

    expect(sheet(shell).classList.contains("unbuilt")).toBe(false);
    expect(sheet(shell).renderRoot.querySelector("g[data-symbol] > title")).not.toBeNull();
    await dragged(shell, SWITCH);

    expect(written()).toContainEqual({
      topic: "tc49/dispatch/point_wanted",
      payload: { addr: "7", position: "thrown" },
    });
  });
});
