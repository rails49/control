/**
 * The properties dialog: a symbol's name, and per kind what only that kind
 * has (EDITOR.md).
 *
 * **A name is typed only where a person has to say it out loud** (ADR-0023).
 * That is a block, which the operator names and the bus carries, and a portal
 * label, which is how a pair of mouths is known to be a pair. Every other name
 * — a turnout's, a slip's, a fixed crossing's, a pin's, a terminal's — is
 * minted and hidden (`named` in model/drawing.ts). A kind left with nothing to
 * edit does not open the dialog at all — an empty modal is worse than none,
 * and the netlist pane is where a hidden name is read.
 *
 * A block's key is the name it is known by everywhere: on the canvas, in the
 * netlist, and as the prefix of every transit id in a trace. Renaming one is a
 * real change and every wire that names its pins is rewritten with it, which
 * is why they are minted short.
 *
 * **Transit names are not edited here.** A drawing can still write one on a
 * symbol's leg and derivation honours it, but the dialog does not offer it: a
 * derived transit is named for the two block ends it joins, and those names
 * carry the context. Dropping the field leaves a fixed crossing with nothing
 * to set at all, so it opens no dialog.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/dialog/dialog.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";
import "@shoelace-style/shoelace/dist/components/option/option.js";
import "@shoelace-style/shoelace/dist/components/select/select.js";

import { PINS } from "../symbols.generated.js";
import { named, type AnyKind, type SymbolSpec } from "../model/drawing.js";
import { propertiesStyles } from "./tc-properties.styles.js";

/** What the dialog hands back: a new name where it changed, and the spec. */
export interface Properties {
  was: string;
  name: string;
  spec: SymbolSpec;
}

@customElement("tc-properties")
export class TcProperties extends LitElement {
  static override styles = propertiesStyles;

  /** The symbol being edited, or null when the dialog is closed. */
  @property({ attribute: false }) editing: { name: string; spec: SymbolSpec } | null =
    null;

  @state() private draft: SymbolSpec = { kind: "block" };
  @state() private name = "";

  override willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("editing") && this.editing !== null) {
      this.draft = structuredClone(this.editing.spec);
      this.name = this.editing.name;
    }
  }

  override render() {
    if (this.editing === null) return nothing;
    return html`
      <sl-dialog open label="Properties" @sl-after-hide=${this.close}>
        ${named(this.draft.kind)
          ? html`
              <sl-input
                label="Name"
                help-text="The id every transit through this symbol is prefixed with."
                value=${this.name}
                @sl-input=${(event: Event) => {
                  this.name = (event.target as HTMLInputElement).value;
                }}
              ></sl-input>
            `
          : nothing}
        ${this.perKind()}
        <sl-button slot="footer" @click=${this.close}>Cancel</sl-button>
        <sl-button slot="footer" variant="primary" @click=${this.apply}>
          Apply
        </sl-button>
      </sl-dialog>
    `;
  }

  private perKind() {
    if (this.draft.kind === "block") return this.block();
    if (this.draft.kind === "portal") {
      return html`
        <sl-input
          label="Portal label"
          help-text="Two portals with the same label join their wires as if directly connected."
          value=${this.draft.label ?? ""}
          @sl-input=${this.take("label")}
        ></sl-input>
      `;
    }
    // Every other kind is drawn one way, so there is nothing per-kind to set.
    return nothing;
  }

  private block() {
    return html`
      <sl-input
        type="number"
        label="Length"
        value=${String(this.draft.length ?? 0)}
        @sl-input=${(event: Event) => {
          this.draft = {
            ...this.draft,
            length: Number((event.target as HTMLInputElement).value),
          };
        }}
      ></sl-input>
      ${PINS.block.map(
        (end) => html`
          <sl-input
            label=${`Sensor ${end}`}
            value=${this.draft.sensors?.[end] ?? ""}
            @sl-input=${(event: Event) =>
              this.sensor(end, (event.target as HTMLInputElement).value)}
          ></sl-input>
        `,
      )}
    `;
  }

  private take(key: "label") {
    return (event: Event) => {
      this.draft = {
        ...this.draft,
        [key]: (event.target as HTMLInputElement).value,
      };
    };
  }

  private sensor(end: string, id: string): void {
    const sensors = { ...this.draft.sensors, [end]: id };
    if (id === "") delete sensors[end];
    this.draft = { ...this.draft, sensors };
  }

  private apply(): void {
    if (this.editing === null) return;
    this.dispatchEvent(
      new CustomEvent<Properties>("properties", {
        detail: { was: this.editing.name, name: this.name, spec: tidy(this.draft) },
        bubbles: true,
        composed: true,
      }),
    );
    this.close();
  }

  private close(): void {
    this.dispatchEvent(
      new CustomEvent("properties-closed", { bubbles: true, composed: true }),
    );
  }
}

/** Whether a kind has anything to edit: a name of its own, or the fields only
 *  a portal has. A pin, a terminal and a fixed crossing have neither, and the
 *  menu offers them no properties. */
export function editable(kind: AnyKind): boolean {
  return named(kind) || kind === "portal";
}

/** Drop what the drawing schema would refuse: an empty label is not a name,
 *  and an empty mapping is a key the file does not need. */
function tidy(spec: SymbolSpec): SymbolSpec {
  const tidied: SymbolSpec = { ...spec };
  if (!tidied.label) delete tidied.label;
  if (tidied.sensors && Object.keys(tidied.sensors).length === 0) {
    delete tidied.sensors;
  }
  if (tidied.names && Object.keys(tidied.names).length === 0) {
    delete tidied.names;
  }
  return tidied;
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-properties": TcProperties;
  }
}
