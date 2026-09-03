# Stock view

The view a person makes cars and trains in: what the railroad owns, and the
rakes made up from it ([#393](https://github.com/rails49/control/issues/393)).
It is one of the app's views of the loaded railroad, the
[run view](PANEL.md), the [throttle](THROTTLE.md) and the [editor](EDITOR.md)
being the others
([ADR-0038](../adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)), and
it edits the railroad's **roster** and the installation's **catalogue** over
the two store routes those documents have
([#388](https://github.com/rails49/control/issues/388),
[#392](https://github.com/rails49/control/issues/392)). Terminology follows
[CONTEXT.md](../../CONTEXT.md), **Stock**.

Until this view existed a person could draw a railroad and save it and then
not put a train on it: the flow the app exists for stopped one step short.

## The screen

Two columns. On the left, what can go in a train: **cars above, models below**.
On the right, the **trains**. You compose right from left.

**Cars are above because they are yours and they are few.** A locomotive you
own, with its address, written once and never restated. **Models are below
because they are what anything is made of**, and ten identical hoppers are one
row rather than ten
([ADR-0061](../adr/0061-stock-with-nothing-of-its-own-is-named-by-its-model.md)).

A **train** is a name and an ordered list of entries, each with a
forward/reverse toggle (`lib/roster.py`, `Coupled`). Its **length, kind and
functions are derived and never authored**
([ADR-0045](../adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)):
they are shown under the name and are not offered for editing. They are
derived *here* as well as by the store, because a train being made up has not
been saved and so has no `/rosters/<railroad>/trains` answer to read; the two
derivations say the same thing, and `ui/test/composing.test.ts` pins them
together.

## What it does

**Adding a model entry** to a train gives an **anonymous item**: the entry
names the model, and there is nothing else to say about it.

**Filling in an address promotes it to a car** in the list above, named from
the model with a suffix you can edit — `arnold-ce68-1` until you call it
`krokodil-a`. Nothing asks you to classify an item before you add it: an
address is the physical identity, and having one is exactly what puts an item
on `cars` (ADR-0061). Two locomotives of one product get two cars and two
addresses, written once, and neither is restated the next time a rake is made
up.

**A car can exist in no train**: a locomotive you own and have not made up a
rake for. Unmaking a train leaves its cars on the roster — composing a train
and owning the stock are two things.

**Kind never implies an address.** A powered van is a real thing
(`layout/interface.py`), so the address field is offered on every entry and
never assumed from what the model is.

**A product that does not exist yet is created in the same dialog** — name,
length over buffers, kind, functions. The catalogue is a real document with
its own route underneath and never a place you navigate to for its own sake. It
is written the moment it is made, ahead of the roster, because a roster naming
a model the installation has not got is refused whole (`store/stock.py`).

**Composing a train and placing it are two actions**
([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)): a rake is durable
and lives in the roster; where it stands belongs to the run. You make it up
here and put it on the layout in the run view.

**Save writes the roster whole.** `PUT /rosters/<railroad>` is the document, so
a car left out is a car removed and removing one needs no verb. The store
validates it against the catalogue and writes nothing where it does not
validate, so a refusal arrives in the validator's own words and is shown on the
screen that caused it.

**Refusals name what holds a thing.** A car a train is made of cannot be
removed, and the message says which train. A model's row says what names it —
the cars that are one, then the trains whose entries do — for the same reason,
read on the row rather than run into: the store's catalogue face has **no
DELETE for any document** and an unused model costs nothing
(`store/server.py`), so this screen offers no way to remove a model at all.

**No session.** Like the editor, this is a document view: it reads and writes
the store, and the bus carries nothing about what a railroad owns
([ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)).

## The length guard

A length lives on the **model** as well as on the **car** — `stock._car` takes
`model.length` unless the car overrides it — so correcting a product's length
changes every item of that product, including the one under a train the
dispatcher is fitting into blocks right now.

So **length editing is disabled for a train the run shows as placed, and for a
model used by such a train**, with the reason said on the control: the field
keeps its box, takes the hint colour, and carries `'ore' is on the layout —
take it off to correct a length` both as its title and beside it. A field that
vanished would leave a person looking for it.

This is a **UI guard in one browser**. `tc-app.ts` holds the run state — which
trains the run view says are placed — and passes it down, the same path the
throttle's cabs take. A second browser editing stock during a run is not
covered, and closing that properly is the same hole as
[#390](https://github.com/rails49/control/issues/390).

## The run view beside it

**The run view re-reads the roster when it becomes the current view.** The
store is not on the bus, so nothing publishes a roster change: a person who
adds a locomotive here and switches to Run must see it. The run keeps the
roster it joined with until then.

Only the roster. The session is joined, the socket is open and every retained
topic has been replayed, so re-joining would take a live picture down to bring
back a document.

## What it is not

**Not a place where a train is placed.** Where a train stands is the run's, and
the run view's roster pane is where a rake goes onto the rails (ADR-0039).

**Not a decoder programmer.** The address is the number already programmed into
that decoder, recorded here so the roster can say which item is which; nothing
on this screen writes to a command station, and which function number a name
sits on is a fact about the product, kept for the translator and never shown
by a view (ADR-0045).

**Not a count of what the railroad owns.** A train may name more hoppers than
there are, and the number drifts the moment an item is bought or broken with
nothing able to tell the software (ADR-0061, *what was rejected*).

## Implementation

`ui/src/ui/tc-stock.ts`, a Lit component in the shape the other views take,
with its styles beside it. It works nothing out: every length, kind, function,
minted name and refusal is `ui/src/model/stock.ts`'s answer, which holds the
two documents and every edit to either and knows nothing about the DOM.

The rows are the browser's own `input` and `select` and the new-model dialog is
Shoelace's, the way the properties dialog is: a dense grid of three fields per
row is a table, and a form is a form.

The view is not in the shell's left-pane slot. `--pane` is the width of the
strip beside a drawing surface — the editor's palette, the run view's roster
([#169](https://github.com/rails49/control/issues/169)) — and this view has no
surface, so it declares its own two columns and leaves `--pane` alone. It puts
nothing in the bar either: `MENUS.stock` and `TOOLS.stock` are empty, there
being no viewport to move, and `File ▸ Save` here would be a second Save
meaning something other than the one beside it.

`ICONS` in `ui/src/ui/icons.ts` is keyed by `ViewId`, so the wagon on the
band's selector is part of this rather than something to remember.

## Tests

Split the way the app's suites are split. `ui/test/composing.test.ts` drives
the model with no DOM — promotion and the name it mints, the derived length,
kind and functions, two locomotives of one product, what holds a car or a
model, and the length guard. `ui/test/making.test.ts` mounts the app in this
view against a store with no `catalogue/` and no roster and drives the
controls: a model written the moment it is made, a train made up of a
locomotive and three hoppers, the document that reaches
`PUT /rosters/<railroad>` with one car entry and three model entries, the guard
killing a field while the run has that train placed, and the run view showing
a train made up here without a reload.
