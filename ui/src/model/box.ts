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

/** Whether the installation says this box can be turned off. Only a `200`
 *  whose JSON body has `can_turn_off === true` is yes; anything else is no,
 *  a rejection included. */
export async function canTurnOff(): Promise<boolean> {
  try {
    const response = await fetch("/box");
    if (response.status !== 200) return false;
    const body = (await response.json()) as unknown;
    return (body as { can_turn_off?: unknown } | null)?.can_turn_off === true;
  } catch {
    return false;
  }
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
