// @vitest-environment happy-dom

/**
 * Turning the box off from the settings dialog (#745).
 *
 * Two parts. The model against a fake `fetch`, because what it reads out of
 * the installation's answers — a yes only on `200` with `can_turn_off: true`,
 * a refusal's words as written — has nothing to do with the dialog. Then the
 * dialog through the app, which draws a **Box** part only where the
 * installation says yes and sends only while the track is dead.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../src/ui/tc-app.js";
import { canTurnOff, turnOff } from "../src/model/box.js";
import type { TcApp } from "../src/ui/tc-app.js";
import type { TcSettings } from "../src/ui/tc-settings.js";
import { mounted, type Reply, serving, settingsOpened, settled } from "./support/shell.js";
import {
  brokering,
  DERIVES,
  joined,
  said,
  STOCK,
  stored,
  unbrokered,
} from "./support/session.js";

const POWER = "tc49/layout/state/power";

/** A `fetch` that answers every call with `status` and `body`, and the calls
 *  it was given. */
function answering(status: number, body: string): { path: string; method: string }[] {
  const calls: { path: string; method: string }[] = [];
  globalThis.fetch = ((path: string, init?: RequestInit) => {
    calls.push({ path, method: init?.method ?? "GET" });
    return Promise.resolve(new Response(body, { status }));
  }) as typeof fetch;
  return calls;
}

/** A `fetch` that rejects, which is what nothing answering looks like. */
function rejecting(): void {
  globalThis.fetch = (() =>
    Promise.reject(new TypeError("Failed to fetch"))) as unknown as typeof fetch;
}

describe("whether the box can be turned off", () => {
  it("is yes on a 200 saying it can", async () => {
    const calls = answering(200, '{"can_turn_off": true}');

    expect(await canTurnOff()).toBe(true);
    expect(calls).toEqual([{ path: "/box", method: "GET" }]);
  });

  it("is no on a 200 saying it cannot", async () => {
    answering(200, '{"can_turn_off": false}');

    expect(await canTurnOff()).toBe(false);
  });

  it("is no on a status that is not ok", async () => {
    answering(404, '{"can_turn_off": true}');

    expect(await canTurnOff()).toBe(false);
  });

  /** What vite answers at `localhost`: its own page, under a 200. */
  it("is no on a 200 that is not JSON", async () => {
    answering(200, "<!doctype html><html></html>");

    expect(await canTurnOff()).toBe(false);
  });

  it("is no on JSON of another shape", async () => {
    answering(200, '{"can_turn_off": "yes"}');
    expect(await canTurnOff()).toBe(false);

    answering(200, "true");
    expect(await canTurnOff()).toBe(false);
  });

  it("is no where nothing answers", async () => {
    rejecting();

    expect(await canTurnOff()).toBe(false);
  });
});

describe("asking for the box to be turned off", () => {
  it("is nothing to say on a 202", async () => {
    const calls = answering(202, "");

    expect(await turnOff()).toBeNull();
    expect(calls).toEqual([{ path: "/box/off", method: "POST" }]);
  });

  it("is the refusal's words as written", async () => {
    answering(409, "the box is already turning off");

    expect(await turnOff()).toBe("the box is already turning off");
  });

  it("is the rejection's own words where nothing answers", async () => {
    rejecting();

    expect(await turnOff()).toBe("Failed to fetch");
  });
});

/** The installation's yes, which is what a box it runs on answers. */
const CAN = { status: 200, body: '{"can_turn_off": true}' };

/** How often the dialog asked for the box to be turned off. */
let asked: number;

beforeEach(() => {
  brokering();
  asked = 0;
});

afterEach(unbrokered);

/** The toy railroad behind the store, as `brokering` has it, and beside it the
 *  installation answering `box` and counting each `POST /box/off` it answers
 *  with `off`. */
function installed(box: Reply, off: Reply | Promise<Reply> = { status: 202, body: "" }): void {
  serving({
    drawings: ["toy"],
    rosterOf: () => STOCK,
    read: stored,
    review: () => Promise.resolve(DERIVES),
    box: () => box,
    off: () => {
      asked += 1;
      return off;
    },
  });
}

/** An app joined to the broker, with the track reading `power`. */
async function powered(power: "on" | "stopped" | "off"): Promise<TcApp> {
  const shell = await joined();
  await said(shell, POWER, { power });
  return shell;
}

function part(dialog: TcSettings): HTMLElement | null {
  return dialog.renderRoot.querySelector<HTMLElement>("div.box");
}

/** One of the Box part's presses, by its class. */
function press(dialog: TcSettings, which: string): HTMLButtonElement | null {
  return dialog.renderRoot.querySelector<HTMLButtonElement>(`div.box sl-button.${which}`);
}

/** What the Box part says beneath its press, `null` where it says nothing. */
function hint(dialog: TcSettings): string | null {
  return dialog.renderRoot.querySelector("div.box .hint")?.textContent?.trim() ?? null;
}

async function pressed(shell: TcApp, dialog: TcSettings, which: string): Promise<void> {
  press(dialog, which)!.click();
  await settled(shell);
}

describe("the dialog's Box part", () => {
  it("is not there where the box answers as localhost does", async () => {
    const shell = await powered("off");

    const dialog = await settingsOpened(shell);

    expect(part(dialog)).toBeNull();
  });

  it("is not there where the installation says no", async () => {
    installed({ status: 200, body: '{"can_turn_off": false}' });
    const shell = await powered("off");

    const dialog = await settingsOpened(shell);

    expect(part(dialog)).toBeNull();
  });

  it("offers the press where the installation says yes", async () => {
    installed(CAN);
    const shell = await powered("off");

    const dialog = await settingsOpened(shell);

    expect(press(dialog, "turn")!.textContent!.trim()).toBe("Turn the box off…");
    expect(press(dialog, "turn")!.hasAttribute("disabled")).toBe(false);
    expect(hint(dialog)).toBeNull();
  });

  it.each(["on", "stopped"] as const)(
    "is dead and says why while the track reads %s",
    async (power) => {
      installed(CAN);
      const shell = await powered(power);

      const dialog = await settingsOpened(shell);

      expect(press(dialog, "turn")!.hasAttribute("disabled")).toBe(true);
      expect(hint(dialog)).toBe(
        "the track has power: switch it off before turning the box off",
      );
    },
  );

  it("is dead and says why while the layout has not said", async () => {
    installed(CAN);
    const shell = await mounted();

    const dialog = await settingsOpened(shell);

    expect(press(dialog, "turn")!.hasAttribute("disabled")).toBe(true);
    expect(hint(dialog)).toBe("the layout has not said whether the track has power");
  });

  it("asks again each time the dialog opens", async () => {
    const shell = await powered("off");
    const shut = await settingsOpened(shell);
    expect(part(shut)).toBeNull();
    shut.dispatchEvent(new CustomEvent("settings-closed", { bubbles: true, composed: true }));
    await settled(shell);
    installed(CAN);

    const dialog = await settingsOpened(shell);

    expect(part(dialog)).not.toBeNull();
  });

  it("asks once more, and Cancel sends nothing", async () => {
    installed(CAN);
    const shell = await powered("off");
    const dialog = await settingsOpened(shell);

    await pressed(shell, dialog, "turn");
    expect(part(dialog)!.querySelector(".asking")!.textContent!.trim()).toBe(
      "Every app on this box stops, and starting it again takes a person at the box.",
    );
    await pressed(shell, dialog, "cancel");

    expect(asked).toBe(0);
    expect(press(dialog, "turn")).not.toBeNull();
  });

  it("sends one request on Turn off, and says to unplug once the lights go out", async () => {
    installed(CAN);
    const shell = await powered("off");
    const dialog = await settingsOpened(shell);

    await pressed(shell, dialog, "turn");
    await pressed(shell, dialog, "off");

    expect(asked).toBe(1);
    expect(hint(dialog)).toBe("The box is turning off. Unplug it once its lights go out.");
    expect(press(dialog, "turn")).toBeNull();
  });

  it("sends nothing where the track got power after the first press", async () => {
    installed(CAN);
    const shell = await powered("off");
    const dialog = await settingsOpened(shell);
    await pressed(shell, dialog, "turn");

    await said(shell, POWER, { power: "on" });
    await pressed(shell, dialog, "off");

    expect(asked).toBe(0);
    expect(press(dialog, "turn")!.hasAttribute("disabled")).toBe(true);
  });

  it("shows a refusal's words and gives the press back", async () => {
    installed(CAN, { status: 409, body: "the box is already turning off" });
    const shell = await powered("off");
    const dialog = await settingsOpened(shell);

    await pressed(shell, dialog, "turn");
    await pressed(shell, dialog, "off");

    expect(part(dialog)!.querySelector(".hint.wrong")!.textContent!.trim()).toBe(
      "the box is already turning off",
    );
    expect(press(dialog, "turn")!.hasAttribute("disabled")).toBe(false);
  });

  it("is dead while the request is out", async () => {
    let answer!: (reply: Reply) => void;
    installed(CAN, new Promise((resolve) => (answer = resolve)));
    const shell = await powered("off");
    const dialog = await settingsOpened(shell);

    await pressed(shell, dialog, "turn");
    await pressed(shell, dialog, "off");

    expect(press(dialog, "turn")!.hasAttribute("disabled")).toBe(true);
    expect(press(dialog, "off")).toBeNull();
    answer({ status: 202, body: "" });
    await settled(shell);
    expect(asked).toBe(1);
  });

  it("keeps the press dead when the dialog is opened again while the request is out", async () => {
    installed(CAN, new Promise(() => {}));
    const shell = await powered("off");
    const shut = await settingsOpened(shell);
    await pressed(shell, shut, "turn");
    await pressed(shell, shut, "off");
    shut.dispatchEvent(new CustomEvent("settings-closed", { bubbles: true, composed: true }));
    await settled(shell);

    const dialog = await settingsOpened(shell);

    expect(press(dialog, "turn")!.hasAttribute("disabled")).toBe(true);
  });
});
