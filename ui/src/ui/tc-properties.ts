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
 * A turnout and a slip are left with something: `addr`, the address the
 * hardware behind the points answers to (ADR-0022). It is what the bus
 * commands them by, so it is theirs to type where their key is not, and their
 * dialog holds it alone. A fixed crossing has no motor and so still holds
 * nothing.
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

import {
  motorised,
  named,
  symbolTrouble,
  type AnyKind,
  type SymbolSpec,
} from "../model/drawing.js";
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

  /** Every name the drawing holds, the one being edited among them. What a
   *  rename is refused against, the dialog being the only place a name is
   *  typed. */
  @property({ attribute: false }) taken: readonly string[] = [];

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
        ${named(this.draft.kind) ? this.nameField() : nothing}
        ${this.perKind()}
        <sl-button slot="footer" @click=${this.close}>Cancel</sl-button>
        <sl-button slot="footer" variant="primary" @click=${this.apply}>
          Apply
        </sl-button>
      </sl-dialog>
    `;
  }

  /** The name field, and why what is in it will not do. The reason stands
   *  where the name was typed rather than in a panel across the screen, and it
   *  is shown as it is typed rather than only on Apply. */
  private nameField() {
    const trouble = this.trouble;
    return html`
      <sl-input
        class=${trouble === null ? "" : "refused"}
        label="Name"
        help-text=${trouble ??
        "The id every transit through this symbol is prefixed with."}
        value=${this.name}
        @sl-input=${(event: Event) => {
          this.name = (event.target as HTMLInputElement).value;
        }}
      ></sl-input>
    `;
  }

  /** Why the typed name will not do, or `null` for one that will. Nothing to
   *  say where the kind has no name to type (model/drawing.ts). */
  private get trouble(): string | null {
    if (this.editing === null || !named(this.draft.kind)) return null;
    return symbolTrouble(this.name, this.editing.name, this.taken);
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
    if (motorised(this.draft.kind)) {
      return html`
        <sl-input
          label="Address"
          help-text="What the points answer to. A DCC accessory number is a string that happens to be digits."
          value=${this.draft.addr ?? ""}
          @sl-input=${this.take("addr")}
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
    `;
  }

  private take(key: "label" | "addr") {
    return (event: Event) => {
      this.draft = {
        ...this.draft,
        [key]: (event.target as HTMLInputElement).value,
      };
    };
  }

  private apply(): void {
    if (this.editing === null) return;
    // A name the drawing will not take leaves the dialog open holding it, so
    // it can be corrected where it was typed (ADR-0023).
    if (this.trouble !== null) return;
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

/** Whether a kind has anything to edit: a name of its own, a portal's label,
 *  or a motor's address. A pin, a terminal and a fixed crossing have none of
 *  them, and the menu offers them no properties. */
export function editable(kind: AnyKind): boolean {
  return named(kind) || kind === "portal" || motorised(kind);
}

/** Drop what the drawing schema would refuse: an empty label is not a name,
 *  and an empty mapping is a key the file does not need. A cleared address is
 *  no address rather than an empty one — a drawing with none is valid. */
function tidy(spec: SymbolSpec): SymbolSpec {
  const tidied: SymbolSpec = { ...spec };
  if (!tidied.label) delete tidied.label;
  if (!tidied.addr) delete tidied.addr;
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
