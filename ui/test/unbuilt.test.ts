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
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import type { TcApp } from "../src/ui/tc-app.js";
import { CLEAN, mounted, rail, serving, session, settled, shows } from "./support/shell.js";
import { Broker, brokering, RAILROAD, said, STOCK, stored, unbrokered } from "./support/session.js";

const POWER = "tc49/layout/state/power";

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
