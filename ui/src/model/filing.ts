/**
 * The editor's dealings with the store: what is open, whether it is saved,
 * what the store last said about it, and what went wrong (#105).
 *
 * Files and review are one module, not two. A refusal and the unsaved dot are
 * written from both halves — a save that did not land and a review that did
 * not answer both read in the band, and both opening a hand-written railroad
 * and drawing on it leave edits to save — so splitting them would put the
 * pair back in the shell as the thing two modules write, and the rule that a
 * refusal lives until the next accepted edit would be enforced in three
 * places instead of one.
 *
 * The store is a dependency, so a test hands over a fake rather than forging
 * an HTTP answer to reach rules that have nothing to do with HTTP. The prompt
 * is not: `model/` has no DOM and a modal question is the shell's, so the
 * shell asks and passes the raw answer over, and this vets it.
 *
 * The `Editor` is taken per call and never held, as `gesture.ts` states the
 * rule and for the same reason: the shell is the single owner of the instance
 * the canvas renders from. The revision guard in `reviewing` still holds — it
 * re-reads `revision` off the instance it was handed.
 */

import { emptyDrawing, nameTrouble, type Drawing } from "./drawing.js";
import type { Editor } from "./editor.js";
import {
  listDrawings,
  readDrawing,
  review,
  saveDrawing,
  type Review,
} from "./store.js";

/** The store's routes, as the editor uses them. */
export interface Store {
  listDrawings(): Promise<string[]>;
  readDrawing(name: string): Promise<Drawing>;
  saveDrawing(drawing: Drawing): Promise<void>;
  review(drawing: Drawing): Promise<Review>;
}

/** The store as it is over HTTP, which is what the editor runs against. */
const live: Store = { listDrawings, readDrawing, saveDrawing, review };

export class Filing {
  private list: readonly string[] = [];
  private name = "";
  private clean = true;
  /** Whether the open drawing is one started here that nothing has happened to
   *  since. It has no file, so `clean` is false and the band's dot is up
   *  telling the truth, but there is nothing on it anyone could lose (#136). */
  private untouched = false;
  private wrong: string | null = null;
  private said: Review | null = null;

  constructor(
    private readonly notify: () => void,
    private readonly store: Store = live,
  ) {}

  /** The drawings there are to open, as the store last listed them. */
  get drawings(): readonly string[] {
    return this.list;
  }

  /** The drawing that is open, `""` while none is. */
  get opened(): string {
    return this.name;
  }

  /** Whether the store has been given every edit. */
  get saved(): boolean {
    return this.clean;
  }

  /** Whether there are edits an operator would recognise as lost: a drawing
   *  edited since it was last written, or a never-written one that has been
   *  drawn on. It is what the question before a discard asks (#101, #136), and
   *  it is not `saved`: a drawing is unsaved from the moment it is started,
   *  the file not existing yet, and asking about a canvas nothing has been
   *  placed on is the dialog that gets dismissed unread — which is how the
   *  question fails on the evening's drawing that it is there for. */
  get edits(): boolean {
    return !this.clean && !this.untouched;
  }

  /** What the editor could not do — the store not answering, a save that did
   *  not land, a name no drawing can wear. It reads in the band, none of it
   *  being a fault of the drawing that the canvas could mark (#84, ADR-0024).
   *  It lives until the next accepted edit, a refusal outliving what caused it
   *  being as wrong as one that never shows. */
  get trouble(): string | null {
    return this.wrong;
  }

  /** What the store last said the drawing means, `null` before it has been
   *  asked. */
  get reviewed(): Review | null {
    return this.said;
  }

  /** Whether the drawing derives, which is the whole of what the band says
   *  about the drawing itself (ADR-0024). Off the store's refusal and nothing
   *  else: an overlap and a symbol still lacking an address derive, and a
   *  drawing nothing has been asked about yet has nothing against it. A store
   *  that stops answering leaves the last review standing, so the mark neither
   *  appears nor clears on a fault that is not the author's. */
  get derives(): boolean {
    return this.said === null || this.said.refused === null;
  }

  /** The drawings there are to open, asked for once on load. */
  async load(): Promise<void> {
    try {
      this.list = await this.store.listDrawings();
      this.wrong = null;
    } catch (failure) {
      this.wrong = `the store is not answering: ${String(failure)}`;
    }
    this.notify();
  }

  /**
   * One drawing, read into the editor and reviewed. It answers whether a
   * drawing arrived, which is what tells the shell to fit the canvas to it:
   * the two DOM touches in this are the shell's and stay there.
   */
  async open(name: string, editor: Editor): Promise<boolean> {
    try {
      editor.reset(await this.store.readDrawing(name));
      this.name = name;
      // Staging is an edit, so a railroad that arrives without placement
      // opens with something to save, and something to lose, rather than
      // something already saved.
      this.clean = !editor.stage();
      this.untouched = false;
      this.wrong = null;
    } catch (failure) {
      this.wrong = String(failure);
      this.notify();
      return false;
    }
    await this.reviewing(editor, true);
    return true;
  }

  /**
   * A named empty canvas, under the name the shell asked for: `untitled` is
   * not a file anyone asked for, and nothing is written until the first save,
   * so an abandoned start leaves no file behind.
   *
   * `said` is the raw answer to the shell's prompt, `null` where the operator
   * closed it without one.
   */
  async create(said: string | null, editor: Editor): Promise<boolean> {
    const name = this.named(said);
    if (name === null) {
      this.notify();
      return false;
    }
    editor.reset(emptyDrawing(name));
    this.name = name;
    this.clean = false;
    this.untouched = true;
    await this.reviewing(editor);
    return true;
  }

  /** The open drawing, given to the store. Saving needs a drawing to save
   *  into: nothing is open until a railroad is chosen, and `untitled` is not a
   *  file anyone asked for. */
  async save(editor: Editor): Promise<void> {
    if (this.name === "") return;
    try {
      await this.store.saveDrawing(editor.drawing);
      this.clean = true;
      this.wrong = null;
      // The first save of a new name is what creates the file, so the list
      // that refuses taken names learns it here.
      if (!this.list.includes(this.name)) {
        this.list = [...this.list, this.name].sort();
      }
    } catch (failure) {
      this.wrong = String(failure);
    }
    this.notify();
  }

  /** The fork: the open drawing, unsaved edits and all, written at once under
   *  a new name. The file under the old name keeps its last-saved state. */
  async saveAs(said: string | null, editor: Editor): Promise<void> {
    if (this.name === "") return;
    const name = this.named(said);
    if (name === null) {
      this.notify();
      return;
    }
    editor.rename(name);
    this.name = name;
    await this.save(editor);
  }

  /** The drawing changed. The dot goes up on the keystroke and the store is
   *  asked afterwards, so nothing waits on a round trip. */
  edited(editor: Editor): void {
    this.clean = false;
    this.untouched = false;
    this.notify();
    void this.reviewing(editor);
  }

  /** One drawing name, as it came back from the shell's prompt, checked. A
   *  refusal reads in the band rather than re-prompting: the prompt is gone by
   *  then, nothing on the canvas is wrong, and asking again is one click away
   *  (ADR-0024). */
  private named(said: string | null): string | null {
    if (said === null) return null;
    const trouble = nameTrouble(said, this.list);
    if (trouble === null) return said;
    this.wrong = trouble;
    return null;
  }

  /**
   * What the store says the open drawing means.
   *
   * A drawing mid-edit is normally not derivable, so a refusal comes back
   * inside a 200 and is held; only a document that will not load at all is an
   * error worth reporting as one.
   *
   * A junction always has a valid name, so the names the drawing has not
   * settled are minted the moment the store says which junctions exist. The
   * write folds into the edit that caused it, and asking again with the names
   * in place is what makes the pane agree with the drawing. Opening is the one
   * review that also replaces the names a person typed (ADR-0023), which
   * happens once, before anything is drawn from the answer.
   */
  private async reviewing(editor: Editor, opening = false): Promise<void> {
    try {
      const at = editor.revision;
      const first = await this.store.review(editor.drawing);
      this.wrong = null;
      const named = opening
        ? editor.remint(first, at)
        : editor.settle(first, at);
      if (named) {
        // Opening a hand-written railroad has edits to save, because the names
        // it was written with are not the ones it now holds. Minting them is
        // an edit like any other, so it clears `untouched` with the dot it
        // puts up (#147).
        this.clean = false;
        this.untouched = false;
        this.said = await this.store.review(editor.drawing);
      } else {
        this.said = first;
      }
    } catch (failure) {
      this.wrong = String(failure);
    }
    this.notify();
  }
}
