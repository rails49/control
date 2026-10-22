/**
 * The properties dialog for a widget: its name, its size, how its words are
 * set, and the kind's own text — a text's default, a button's payload, a
 * toggle's on and off (EDITOR.md#properties, ADR-0087).
 *
 * **A widget's name is typed**, unlike a turnout's: it ends the widget's
 * topic, and whoever writes the listener or the script has to say it. So the
 * dialog shows the whole topic beside it, read-only and selectable, and the
 * topic follows the name as it is typed — a rename is a new topic, and it is
 * read here before Apply rather than found out on the bus.
 *
 * What the store would refuse is refused here, beside the field it was typed
 * in, as the symbol dialog does (ADR-0023): a name that is not one topic level
 * or that another widget has, a size that is not two positive whole numbers,
 * and a toggle whose on and off are the same. Apply does nothing until all of
 * them are gone, and the old name stays.
 */

import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { lookTheme } from "@rails49/look";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/input/input.js";
import "@shoelace-style/shoelace/dist/components/option/option.js";
import "@shoelace-style/shoelace/dist/components/select/select.js";

import type { WidgetSpec } from "../model/drawing.js";
import {
  sizeTrouble,
  toggleTrouble,
  widgetTopic,
  widgetTrouble,
  WIDGET_ALIGN,
  WIDGET_TEXT,
} from "../model/widgets.js";
import { propertiesStyles } from "./tc-properties.styles.js";

/** What the dialog hands back: a new name where it changed, and the spec. */
export interface WidgetProperties {
  was: string;
  name: string;
  spec: WidgetSpec;
}

/** The kind's own text fields, by the key each writes. */
const TEXTS: Record<WidgetSpec["kind"], { key: "default" | "payload" | "on" | "off"; label: string; help: string }[]> = {
  text: [
    { key: "default", label: "Default", help: "Shown until a row arrives." },
  ],
  button: [
    { key: "payload", label: "Payload", help: "What a press sends, as typed." },
  ],
  toggle: [
    { key: "on", label: "On", help: "What switching it on sends, as typed." },
    { key: "off", label: "Off", help: "What switching it off sends. It differs from On." },
  ],
};

@customElement("tc-widget-properties")
export class TcWidgetProperties extends LitElement {
  static override styles = [lookTheme, propertiesStyles];

  /** The widget being edited, or null when the dialog is closed. */
  @property({ attribute: false }) editing: { name: string; spec: WidgetSpec } | null =
    null;

  /** Every widget's name, the one being edited among them: what a rename is
   *  refused against. */
  @property({ attribute: false }) taken: readonly string[] = [];

  @state() private draft: WidgetSpec = { kind: "text", at: [0, 0], size: [3, 1] };
  @state() private name = "";

  override willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("editing") && this.editing !== null) {
      this.draft = structuredClone(this.editing.spec);
      this.name = this.editing.name;
    }
  }

  override render() {
    if (this.editing === null) return nothing;
    const named = this.nameTrouble;
    const sized = sizeTrouble(this.draft.size);
    return html`
      <look-dialog open label="Properties" @sl-after-hide=${this.close}>
        <sl-input
          class=${named === null ? "" : "refused"}
          label="Name"
          help-text=${named ?? "Letters, digits, '_' and '-'. It ends the topic."}
          value=${this.name}
          @sl-input=${(event: Event) => {
            this.name = (event.target as HTMLInputElement).value;
          }}
        ></sl-input>
        <sl-input
          label="Topic"
          help-text="Where its row is on the bus, to copy into a listener or a script."
          readonly
          value=${widgetTopic(this.draft.kind, this.name)}
        ></sl-input>
        <sl-input
          type="number"
          class=${sized === null ? "" : "refused"}
          label="Width"
          value=${String(this.draft.size[0])}
          @sl-input=${this.sized(0)}
        ></sl-input>
        <sl-input
          type="number"
          class=${sized === null ? "" : "refused"}
          label="Height"
          help-text=${sized ?? "In squares."}
          value=${String(this.draft.size[1])}
          @sl-input=${this.sized(1)}
        ></sl-input>
        <sl-select
          label="Text size"
          value=${this.draft.text ?? "normal"}
          @sl-change=${(event: Event) => {
            this.draft = {
              ...this.draft,
              text: (event.target as HTMLSelectElement).value as WidgetSpec["text"] & string,
            };
          }}
        >
          ${WIDGET_TEXT.map((one) => html`<sl-option value=${one}>${one}</sl-option>`)}
        </sl-select>
        <sl-select
          label="Alignment"
          value=${this.draft.align ?? "center"}
          @sl-change=${(event: Event) => {
            this.draft = {
              ...this.draft,
              align: (event.target as HTMLSelectElement).value as WidgetSpec["align"] & string,
            };
          }}
        >
          ${WIDGET_ALIGN.map((one) => html`<sl-option value=${one}>${one}</sl-option>`)}
        </sl-select>
        ${TEXTS[this.draft.kind].map((field) => this.text(field))}
        <sl-button slot="footer" @click=${this.close}>Cancel</sl-button>
        <sl-button slot="footer" variant="primary" @click=${this.apply}>
          Apply
        </sl-button>
      </look-dialog>
    `;
  }

  /** Why the name in the field will not do, or `null` where it will. */
  private get nameTrouble(): string | null {
    if (this.editing === null) return null;
    return widgetTrouble(this.name, this.editing.name, this.taken);
  }

  /** One of the kind's own texts. A toggle's Off says why where it is the
   *  same as On, the two being what a page tells the position by. */
  private text(field: (typeof TEXTS)[keyof typeof TEXTS][number]) {
    const trouble = field.key === "off" ? toggleTrouble(this.draft) : null;
    return html`
      <sl-input
        class=${trouble === null ? "" : "refused"}
        label=${field.label}
        help-text=${trouble ?? field.help}
        value=${this.draft[field.key] ?? ""}
        @sl-input=${(event: Event) => {
          this.draft = {
            ...this.draft,
            [field.key]: (event.target as HTMLInputElement).value,
          };
        }}
      ></sl-input>
    `;
  }

  private sized(index: 0 | 1) {
    return (event: Event) => {
      const size: [number, number] = [...this.draft.size];
      size[index] = Number((event.target as HTMLInputElement).value);
      this.draft = { ...this.draft, size };
    };
  }

  private apply(): void {
    if (this.editing === null) return;
    if (
      this.nameTrouble !== null ||
      sizeTrouble(this.draft.size) !== null ||
      toggleTrouble(this.draft) !== null
    ) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<WidgetProperties>("widget-properties", {
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

/** A text widget's empty default is no default, which is how a new one is
 *  written; a button's payload and a toggle's on and off are kept even empty,
 *  the store needing them. */
function tidy(spec: WidgetSpec): WidgetSpec {
  const tidied: WidgetSpec = { ...spec };
  if (!tidied.default) delete tidied.default;
  return tidied;
}

declare global {
  interface HTMLElementTagNameMap {
    "tc-widget-properties": TcWidgetProperties;
  }
}
