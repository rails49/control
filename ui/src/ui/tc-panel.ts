/**
 * The panel, fed by a recorded trace (ui/PANEL.md, #70): the drawing with the
 * run's state painted on top, and play/step control over the trace.
 *
 * Everything shown is the panel model's answer (model/panel.ts) — this
 * component loads the drawing and its `/review` from the store, reads a trace
 * file, feeds events through the model, and paints. It computes nothing:
 * occupancy, aspects, markers and lit legs arrive as data, which is what lets
 * the live panel later swap the trace for the bridge without touching either.
 */

import { LitElement, html, svg, nothing } from "lit";
import { customElement, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/select/select.js";
import "@shoelace-style/shoelace/dist/components/option/option.js";
import "@shoelace-style/shoelace/dist/themes/light.css";

import { pinsOf, wirePins, type Drawing } from "../model/drawing.js";
import { anchorOf, centreOf, transformOf } from "../model/geometry.js";
import { Panel, type BlockView, type Marker } from "../model/panel.js";
import { arrowPose, fitBox } from "../model/scene.js";
import { listDrawings, readDrawing, review } from "../model/store.js";
import { parseTrace, Replay } from "../model/trace.js";
import { pointOf } from "../model/under.js";
import { artwork, DEFS } from "../render/artwork.js";
import { panelStyles } from "./styles.js";

@customElement("tc-panel")
export class TcPanel extends LitElement {
  static override styles = panelStyles;

  @state() private drawings: string[] = [];
  @state() private drawing: Drawing | null = null;
  @state() private traceName: string | null = null;
  @state() private playing = false;
  @state() private rate = 2; // ticks per second
  @state() private trouble: string | null = null;
  /** Bumped after each step: the model mutates in place, so rendering is
   *  asked for rather than observed. */
  @state() private beat = 0;

  private panel: Panel | null = null;
  private replay: Replay | null = null;
  private timer: number | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    void this.start();
  }

  override disconnectedCallback(): void {
    this.pause();
    super.disconnectedCallback();
  }

  private async start(): Promise<void> {
    try {
      this.drawings = await listDrawings();
    } catch {
      this.trouble = "the store is not answering — run `tc49 serve`";
    }
  }

  /** Load a drawing and what it means. The panel needs the derived layout,
   *  so a drawing the store refuses to derive is trouble, not a canvas. */
  private async pick(name: string): Promise<void> {
    this.pause();
    try {
      const drawing = await readDrawing(name);
      const reviewed = await review(drawing);
      if (reviewed.layout === null || reviewed.explain === null) {
        this.trouble = reviewed.refused ?? `'${name}' does not derive`;
        return;
      }
      this.panel = new Panel(reviewed.layout, reviewed.explain);
      this.replay?.restart();
      this.drawing = drawing;
      this.trouble = null;
      this.beat++;
    } catch (error) {
      this.trouble = String(error instanceof Error ? error.message : error);
    }
  }

  private async opened(input: HTMLInputElement): Promise<void> {
    const file = input.files?.[0];
    if (file === undefined) return;
    this.pause();
    try {
      this.replay = new Replay(parseTrace(await file.text()));
      this.panel?.reset();
      this.traceName = file.name;
      this.trouble = null;
      this.beat++;
    } catch (error) {
      this.trouble = `${file.name}: ${error instanceof Error ? error.message : error}`;
    }
    input.value = "";
  }

  private step(): void {
    if (this.panel === null || this.replay === null) return;
    for (const event of this.replay.step()) this.panel.apply(event);
    if (this.replay.done) this.pause();
    this.beat++;
  }

  private play(): void {
    if (this.playing || this.replay === null) return;
    this.playing = true;
    this.timer = window.setInterval(() => this.step(), 1000 / this.rate);
  }

  private pause(): void {
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
    this.playing = false;
  }

  private restart(): void {
    this.pause();
    this.replay?.restart();
    this.panel?.reset();
    this.beat++;
  }

  private paced(rate: number): void {
    this.rate = rate;
    if (this.playing) {
      this.pause();
      this.play();
    }
  }

  override render() {
    const ready = this.panel !== null && this.replay !== null;
    return html`
      <header>
        <sl-select
          size="small"
          placeholder="railroad…"
          hoist
          .value=${this.drawing?.drawing ?? ""}
          @sl-change=${(event: Event) =>
            this.pick((event.target as HTMLSelectElement).value)}
        >
          ${this.drawings.map(
            (name) => html`<sl-option value=${name}>${name}</sl-option>`,
          )}
        </sl-select>
        <sl-button
          size="small"
          @click=${() =>
            (this.renderRoot.querySelector("input[type=file]") as HTMLInputElement).click()}
        >
          Open trace…
        </sl-button>
        <input
          type="file"
          accept=".jsonl,application/jsonl,text/plain"
          hidden
          @change=${(event: Event) => this.opened(event.target as HTMLInputElement)}
        />
        <span>${this.traceName ?? nothing}</span>
        <span class="spacer"></span>
        ${this.trouble === null
          ? nothing
          : html`<span class="trouble">${this.trouble}</span>`}
        <sl-button size="small" ?disabled=${!ready} @click=${this.restart}>
          Restart
        </sl-button>
        <sl-button
          size="small"
          ?disabled=${!ready || this.playing}
          @click=${this.step}
        >
          Step
        </sl-button>
        <sl-button size="small" ?disabled=${!ready} @click=${() =>
          this.playing ? this.pause() : this.play()}>
          ${this.playing ? "Pause" : "Play"}
        </sl-button>
        <label class="rate">
          <input
            type="range"
            min="0.5"
            max="10"
            step="0.5"
            .value=${String(this.rate)}
            @input=${(event: Event) =>
              this.paced(Number((event.target as HTMLInputElement).value))}
          />
          ${this.rate}/s
        </label>
        <span class="tick">
          ${this.replay?.tick === null || this.replay === null
            ? "—"
            : `tick ${this.replay.tick}`}
        </span>
      </header>
      <main>${this.canvas()}</main>
    `;
  }

  private canvas() {
    if (this.drawing === null || this.panel === null) return nothing;
    const { x, y, w, h } = fitBox(this.drawing);
    const blocks = this.panel.blocks();
    const lit = this.panel.litLegs();
    const green = this.panel.greenEnds();
    return svg`
      <svg viewBox=${`${x} ${y} ${w} ${h}`}>
        <defs>${DEFS}</defs>
        <rect class="sheet" x=${x} y=${y} width=${w} height=${h} />
        ${this.wires()} ${this.symbols(blocks, lit, green)}
        ${this.labels(blocks)} ${this.arrows(blocks)} ${this.markers()}
      </svg>
    `;
  }

  private wires() {
    const drawing = this.drawing!;
    return drawing.wires.map((wire) => {
      const [a, b] = wirePins(wire);
      const from = pointOf(drawing, a);
      const to = pointOf(drawing, b);
      if (from === null || to === null) return nothing;
      return svg`<line class="wire" x1=${from.x} y1=${from.y}
                       x2=${to.x} y2=${to.y} />`;
    });
  }

  private symbols(
    blocks: Map<string, BlockView>,
    lit: Map<string, Set<string>>,
    green: Set<string>,
  ) {
    return Object.entries(this.drawing!.symbols).map(([name, spec]) => {
      const block = blocks.get(name);
      const aspects = ["A", "B"]
        .filter((end) => green.has(`${name}.${end}`))
        .map((end) => `green-${end}`);
      const classes = ["symbol", block?.state ?? "", ...aspects]
        .filter((one) => one !== "" && one !== "free")
        .join(" ");
      return svg`
        <g class=${classes} transform=${transformOf(spec)}>
          ${artwork(spec, lit.get(name))}
        </g>
      `;
    });
  }

  /** A block's text, upright outside the turned group: its train when one
   *  stands there, its own name dimly otherwise. */
  private labels(blocks: Map<string, BlockView>) {
    return Object.entries(this.drawing!.symbols).map(([name, spec]) => {
      if (spec.kind !== "block") return nothing;
      const view = blocks.get(name);
      const { x, y } = centreOf(spec);
      return view?.state === "occupied" && view.train !== undefined
        ? svg`<text class="name train" x=${x} y=${y}>${view.train}</text>`
        : svg`<text class="name" x=${x} y=${y}>${spec.label || name}</text>`;
    });
  }

  /** The direction arrow: on the track, ahead of the block's centre, pointing
   *  at the end the train faces. Unknown until a granted move has said. */
  private arrows(blocks: Map<string, BlockView>) {
    return [...blocks].map(([name, view]) => {
      const spec = this.drawing!.symbols[name];
      if (spec === undefined || view.toward === undefined) return nothing;
      const { x, y, angle } = arrowPose(spec, view.toward);
      return svg`<path class="arrow" d="M0.28 0 L-0.14 0.17 L-0.14 -0.17 Z"
        transform=${`translate(${x} ${y}) rotate(${angle})`} />`;
    });
  }

  /** Request endpoints, ring by ring, with the reasons the model worded. */
  private markers() {
    return (this.panel?.markers() ?? []).map((marker) => this.marked(marker));
  }

  private marked(marker: Marker) {
    const dot = marker.at.lastIndexOf(".");
    const spec = this.drawing!.symbols[marker.at.slice(0, dot)];
    if (spec === undefined) return nothing;
    const end = marker.at.slice(dot + 1);
    if (!pinsOf(spec).includes(end)) return nothing;
    const { x, y } = anchorOf(spec, end);
    return svg`
      <circle class=${`marker ${marker.role}`} cx=${x} cy=${y} r="0.3" />
      ${
        marker.note === undefined
          ? nothing
          : svg`<text class=${`note ${marker.role}`} x=${x} y=${y + 0.7}>
              ${marker.note}
            </text>`
      }
    `;
  }
}
