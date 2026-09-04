// @vitest-environment happy-dom

/**
 * What the properties dialog holds, per kind (EDITOR.md#properties).
 *
 * A DOM test at the dialog's own seam: it is handed a symbol and answers with
 * the spec to write back, and which fields it offers is the whole of what a
 * kind can be given. The shell around it is `refusals.test.ts`.
 */

import { describe, expect, it } from "vitest";

import "../src/ui/tc-properties.js";
import type { Properties, TcProperties } from "../src/ui/tc-properties.js";
import type { SymbolSpec } from "../src/model/drawing.js";
import type SlInput from "@shoelace-style/shoelace/dist/components/input/input.js";

/** The dialog, opened on one symbol. */
async function opened(name: string, spec: SymbolSpec): Promise<TcProperties> {
  const dialog = document.createElement("tc-properties");
  dialog.editing = { name, spec };
  dialog.taken = [name];
  document.body.append(dialog);
  await dialog.updateComplete;
  return dialog;
}

/** The labels of the fields the dialog is showing, in order. */
function fields(dialog: TcProperties): string[] {
  return [...dialog.renderRoot.querySelectorAll<SlInput>("sl-input")].map(
    (input) => input.label,
  );
}

function field(dialog: TcProperties, label: string): SlInput {
  return [...dialog.renderRoot.querySelectorAll<SlInput>("sl-input")].find(
    (input) => input.label === label,
  )!;
}

/** Type into a field, the way a keystroke reaches it. */
async function typed(
  dialog: TcProperties,
  label: string,
  value: string,
): Promise<void> {
  const input = field(dialog, label);
  input.value = value;
  input.dispatchEvent(new CustomEvent("sl-input"));
  await dialog.updateComplete;
}

/** Press Apply, and answer with what the dialog handed back. */
async function applied(dialog: TcProperties): Promise<Properties> {
  const handed = new Promise<Properties>((resolve) => {
    dialog.addEventListener("properties", (event) =>
      resolve((event as CustomEvent<Properties>).detail),
    );
  });
  const buttons = [...dialog.renderRoot.querySelectorAll("sl-button")];
  (buttons.find((one) => one.textContent!.trim() === "Apply") as HTMLElement).click();
  return handed;
}

/**
 * A turnout and a slip are addressed by `addr` rather than by their key
 * (ADR-0022), so the address is the one thing the dialog asks them for.
 */
describe("a motorised symbol", () => {
  it("is asked for its address and for nothing else", async () => {
    for (const kind of ["turnout", "single_slip", "double_slip"] as const) {
      expect(fields(await opened("sw1", { kind }))).toEqual(["Address"]);
    }
  });

  it("keeps the address it already carries", async () => {
    const dialog = await opened("sw1", { kind: "turnout", addr: "31" });
    expect(field(dialog, "Address").value).toBe("31");
  });

  it("takes a typed address back into the drawing", async () => {
    const dialog = await opened("sw1", { kind: "turnout", at: [0, 0] });
    await typed(dialog, "Address", "31");
    expect((await applied(dialog)).spec).toEqual({
      kind: "turnout",
      at: [0, 0],
      addr: "31",
    });
  });

  /** Nothing checks an address: what a physical point answers to is not
   *  knowledge the drawing can hold, so `LH-3/2` is as good as `31`. */
  it("takes an address that is not a number", async () => {
    const dialog = await opened("sw1", { kind: "turnout" });
    await typed(dialog, "Address", "LH-3/2");
    expect((await applied(dialog)).spec.addr).toBe("LH-3/2");
  });

  /** An empty field is no address rather than an empty one: the schema takes
   *  a drawing with none, and a key holding "" would be a third state. */
  it("writes no address at all where the field was cleared", async () => {
    const dialog = await opened("sw1", { kind: "turnout", addr: "31" });
    await typed(dialog, "Address", "");
    expect((await applied(dialog)).spec).not.toHaveProperty("addr");
  });
});

/** A fixed crossing has no motor, so there is nothing for an address to answer
 *  to and nothing else it can be given either. */
describe("a fixed crossing", () => {
  it("is asked for nothing", async () => {
    for (const kind of ["crossing", "crossing_90", "crossing_90d"] as const) {
      expect(fields(await opened("x1", { kind }))).toEqual([]);
    }
  });
});

/** A sensor is addressed by the block end it watches, so there is no id to
 *  type for one (ADR-0043). A signal is not: it is fixed wiring standing at
 *  one end, and the address it answers to is typed here the way a turnout's
 *  is (ADR-0022, #286). */
describe("a block", () => {
  it("is asked for its name, its length and a signal at each end", async () => {
    const dialog = await opened("b1", { kind: "block", length: 1000 });
    expect(fields(dialog)).toEqual(["Name", "Length", "Signal at A", "Signal at B"]);
  });

  it("keeps the signal addresses it already carries", async () => {
    const dialog = await opened("b1", {
      kind: "block",
      length: 1000,
      signals: { A: "40", B: "41" },
    });
    expect(field(dialog, "Signal at A").value).toBe("40");
    expect(field(dialog, "Signal at B").value).toBe("41");
  });

  it("shows nothing at an end no signal stands at", async () => {
    const dialog = await opened("b1", {
      kind: "block",
      length: 1000,
      signals: { B: "41" },
    });
    expect(field(dialog, "Signal at A").value).toBe("");
  });

  it("takes a typed signal address back into the drawing", async () => {
    const dialog = await opened("b1", { kind: "block", length: 1000 });
    await typed(dialog, "Signal at B", "41");
    expect((await applied(dialog)).spec).toEqual({
      kind: "block",
      length: 1000,
      signals: { B: "41" },
    });
  });

  /** The round trip: a drawing carrying signals is opened, applied untouched,
   *  and hands back exactly what it was given. */
  it("round-trips the signals it was opened on", async () => {
    const spec: SymbolSpec = {
      kind: "block",
      length: 1000,
      at: [2, 4],
      signals: { A: "40", B: "41" },
    };
    const dialog = await opened("b1", spec);
    expect((await applied(dialog)).spec).toEqual(spec);
  });

  /** An empty field is no signal rather than an empty address, the way a
   *  cleared turnout address is no address: an end carries one or it does
   *  not, and the schema takes a block with neither. */
  it("writes no signal at all where the field was cleared", async () => {
    const dialog = await opened("b1", {
      kind: "block",
      length: 1000,
      signals: { A: "40" },
    });
    await typed(dialog, "Signal at A", "");
    expect((await applied(dialog)).spec).not.toHaveProperty("signals");
  });

  it("keeps the other end's signal when one is cleared", async () => {
    const dialog = await opened("b1", {
      kind: "block",
      length: 1000,
      signals: { A: "40", B: "41" },
    });
    await typed(dialog, "Signal at A", "");
    expect((await applied(dialog)).spec.signals).toEqual({ B: "41" });
  });
});

describe("a portal", () => {
  it("is asked for the label that pairs it with its mate", async () => {
    expect(fields(await opened("p1", { kind: "portal" }))).toEqual([
      "Portal label",
    ]);
  });
});
