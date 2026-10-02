/**
 * PROTOTYPE — throwaway, never merged to main (#628).
 *
 * Three variants of how a model's photo appears in the stock view, switchable
 * with `?variant=A|B|C` and the bar at the bottom of the screen:
 *
 *   A  a thumbnail on each row; the photo and the camera in a dialog
 *   B  the models list as a gallery of tiles; the camera inside the tile
 *   C  rows stay text; a pane beside them shows the picked model's photo
 *
 * Nothing is stored. The camera is a stub: a press waits 1.2 s and answers
 * one of two fixed pictures, or fails when the bar says it does. Saved photos
 * live in memory and go on reload.
 */

import { css, html, nothing, type ReactiveController, type ReactiveControllerHost } from "lit";

import take1 from "./take-1.jpg?url";
import take2 from "./take-2.jpg?url";

export const VARIANTS = [
  { key: "A", name: "thumbnail in the row, photo in a dialog" },
  { key: "B", name: "models as a gallery, camera in the tile" },
  { key: "C", name: "text rows, a photo pane beside them" },
];

export function variant(): string {
  const asked = new URLSearchParams(location.search).get("variant");
  return VARIANTS.some((v) => v.key === asked) ? asked! : "A";
}

type Capture =
  | { model: string; phase: "taking" }
  | { model: string; phase: "shown"; url: string }
  | { model: string; phase: "failed"; why: string };

export class PhotoProto implements ReactiveController {
  shots: Record<string, string> = {};
  capture: Capture | null = null;
  /** A: the model whose dialog is open. C: the model the pane shows. */
  open: string | null = null;
  failing = false;
  private takes = 0;
  private seeded = false;

  constructor(private host: ReactiveControllerHost) {
    host.addController(this);
  }

  hostConnected(): void {
    window.addEventListener("prototype-variant", this.reset);
    window.addEventListener("prototype-camera", this.camera);
  }

  hostDisconnected(): void {
    window.removeEventListener("prototype-variant", this.reset);
    window.removeEventListener("prototype-camera", this.camera);
  }

  private reset = () => {
    this.open = null;
    this.capture = null;
    this.host.requestUpdate();
  };

  private camera = (event: Event) => {
    this.failing = (event as CustomEvent<boolean>).detail;
  };

  /** One model starts with a photo so both states are on screen. */
  seed(models: string[]): void {
    if (this.seeded || models.length === 0) return;
    this.shots[models[0]] = take1;
    this.seeded = true;
  }

  take(model: string): void {
    this.capture = { model, phase: "taking" };
    this.host.requestUpdate();
    setTimeout(() => {
      if (this.capture?.model !== model) return;
      this.capture = this.failing
        ? { model, phase: "failed", why: "502 Bad Gateway — nothing answers /camera/snapshot" }
        : { model, phase: "shown", url: this.takes++ % 2 === 0 ? take1 : take2 };
      this.host.requestUpdate();
    }, 1200);
  }

  save(): void {
    if (this.capture?.phase === "shown") this.shots[this.capture.model] = this.capture.url;
    this.capture = null;
    this.host.requestUpdate();
  }

  discard(): void {
    this.capture = null;
    this.host.requestUpdate();
  }

  show(model: string | null): void {
    this.open = model;
    this.capture = null;
    this.host.requestUpdate();
  }
}

/** A small picture, or an empty box saying there is none. */
export function thumb(p: PhotoProto, model: string, press?: () => void) {
  const url = p.shots[model];
  return html`<button class="thumb" title="photo of ${model}" @click=${press}>
    ${url ? html`<img src=${url} alt="" />` : html`<span>no photo</span>`}
  </button>`;
}

/** The photo, or what the camera is doing, and the presses that go with it. */
export function stage(p: PhotoProto, model: string, small = false) {
  const c = p.capture?.model === model ? p.capture : null;
  const url = p.shots[model];
  const frame = (inner: unknown, extra = "") =>
    html`<div class=${`frame ${small ? "small" : ""} ${extra}`}>${inner}</div>`;
  if (c?.phase === "taking") {
    return html`${frame(html`<span>taking a picture…</span>`, "busy")}
      <div class="presses"><button disabled>Take photo</button></div>`;
  }
  if (c?.phase === "shown") {
    return html`${frame(html`<img src=${c.url} alt="" />`, "unsaved")}
      <p class="note">not saved yet${url ? " — Save replaces the photo it has" : ""}</p>
      <div class="presses">
        <button class="primary" @click=${() => p.save()}>Save</button>
        <button @click=${() => p.take(model)}>Retake</button>
        <button @click=${() => p.discard()}>Cancel</button>
      </div>`;
  }
  if (c?.phase === "failed") {
    return html`${frame(url ? html`<img src=${url} alt="" />` : html`<span>no photo</span>`)}
      <p class="trouble">no picture: ${c.why}</p>
      <div class="presses">
        <button @click=${() => p.take(model)}>Try again</button>
        <button @click=${() => p.discard()}>Cancel</button>
      </div>`;
  }
  return html`${frame(
      url
        ? html`<img src=${url} alt="" />`
        : html`<span>no photo — set one on the photo spot and press Take photo</span>`,
    )}
    <div class="presses">
      <button @click=${() => p.take(model)}>${url ? "Retake photo" : "Take photo"}</button>
    </div>`;
}

/** A: the dialog a thumbnail opens. */
export function photoDialog(p: PhotoProto) {
  const model = p.open;
  if (model === null) return nothing;
  return html`<sl-dialog open label=${`Photo — ${model}`} @sl-after-hide=${() => p.show(null)}>
    ${stage(p, model)}
  </sl-dialog>`;
}

export interface Tile {
  model: string;
  kind: string;
  length: number;
  holders: string[];
}

/** B: the models section as tiles. */
export function gallery(
  p: PhotoProto,
  tiles: Tile[],
  head: unknown,
  add: (model: string) => void,
  addTitle: string,
  canAdd: boolean,
) {
  return html`<section class="models">
    ${head}
    <div class="gallery">
      ${tiles.map(
        (t) => html`<article class="tile">
          ${stage(p, t.model, true)}
          <div class="caption">
            <span class="what">${t.model}</span>
            <button class="add" title=${addTitle} ?disabled=${!canAdd} @click=${() => add(t.model)}>
              +
            </button>
          </div>
          <span class="of">
            ${t.kind} · ${t.length} mm${t.holders.length ? ` — ${t.holders.join(", ")}` : ""}
          </span>
        </article>`,
      )}
    </div>
  </section>`;
}

/** C: the pane between the lists and the trains. */
export function pane(p: PhotoProto, facts: Tile | null) {
  if (facts === null) {
    return html`<aside class="pane">
      <p class="hint">pick a model or a car to see its photo</p>
    </aside>`;
  }
  return html`<aside class="pane">
    <header class="head"><h2>${facts.model}</h2></header>
    ${stage(p, facts.model)}
    <p class="of">${facts.kind} · ${facts.length} mm</p>
    <p class="of">${facts.holders.length ? `in ${facts.holders.join(", ")}` : "in no train"}</p>
  </aside>`;
}

export const photoStyles = css`
  :host([photo-c]) {
    grid-template-columns: minmax(20rem, 28rem) minmax(16rem, 26rem) 1fr;
  }

  li.car.thumbed,
  li.product.thumbed {
    grid-template-columns: 3.2rem 1fr 5rem 5rem auto auto;
  }

  li.picked {
    background: color-mix(in srgb, var(--ink) 8%, transparent);
  }

  li.pickable {
    cursor: pointer;
  }

  button.thumb {
    width: 3.2rem;
    height: 1.8rem;
    padding: 0;
    overflow: hidden;
    border: 1px solid var(--rule);
    background: var(--paper);
    font-size: 0.55rem;
    color: var(--hint);
  }

  button.thumb img,
  .frame img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .frame {
    aspect-ratio: 16 / 9;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--rule);
    border-radius: 3px;
    overflow: hidden;
    color: var(--hint);
    font-size: 0.8rem;
    text-align: center;
  }

  .frame.busy {
    border-style: dashed;
  }

  .frame.unsaved {
    outline: 2px dashed var(--ink);
    outline-offset: 2px;
  }

  .frame.small {
    font-size: 0.65rem;
  }

  .presses {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.4rem;
  }

  .presses button.primary {
    font-weight: 600;
  }

  .note,
  .trouble {
    margin: 0.3rem 0 0;
    font-size: 0.75rem;
  }

  .note {
    color: var(--hint);
  }

  .gallery {
    flex: 1;
    overflow-y: auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
    gap: 0.6rem;
    padding: 0.2rem;
  }

  .tile {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .tile .caption {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }

  .tile .caption .what {
    flex: 1;
  }

  aside.pane {
    padding: 0.4rem;
    border-right: 1px solid var(--rule);
    overflow-y: auto;
  }

  aside.pane .of {
    margin: 0.3rem 0 0;
  }
`;
