/**
 * The box this page is served from, as the installation answers for it
 * (#745, rails49/.github#32).
 *
 * Not the store: the installation answers these routes, on the page's own
 * origin, and only on a box it runs on. A development machine at `localhost`
 * has none, and vite answers its own page there under a 200, which reads as
 * no.
 */

import { said } from "./store.js";

/** The JSON body of a `200` to `GET /box`, `null` for any other answer, a
 *  body that is not JSON and a rejection included. */
async function box(): Promise<{ can_turn_off?: unknown; update?: unknown } | null> {
  try {
    const response = await fetch("/box");
    if (response.status !== 200) return null;
    return (await response.json()) as { can_turn_off?: unknown; update?: unknown } | null;
  } catch {
    return null;
  }
}

/** Whether the installation says this box can be turned off. Only a `200`
 *  whose JSON body has `can_turn_off === true` is yes; anything else is no,
 *  a rejection included. */
export async function canTurnOff(): Promise<boolean> {
  return (await box())?.can_turn_off === true;
}

/** The release the box's status page at `/box/` offers "Update to" for
 *  (#1259): a `200` whose JSON `update` is a string; `null` for anything
 *  else, a rejection included. */
export async function update(): Promise<string | null> {
  const release = (await box())?.update;
  return typeof release === "string" ? release : null;
}

/** Ask the installation to turn the box off: `null` on a `202`, otherwise the
 *  line of text it refused with, as written, or a rejected `fetch`'s own
 *  words. */
export async function turnOff(): Promise<string | null> {
  let response: Response;
  try {
    response = await fetch("/box/off", { method: "POST" });
  } catch (failure) {
    return said(failure);
  }
  if (response.status === 202) return null;
  return await response.text();
}
