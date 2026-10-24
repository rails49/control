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
[GLOSSARY.md](../../GLOSSARY.md), **Stock**.

Until this view existed a person could draw a railroad and save it and then
not put a train on it: the flow the app exists for stopped one step short.

## The screen

As [stock-mockup.html](images/stock-mockup.html) lays it out, in the
throttle's visual style ([#978](https://github.com/rails49/control/issues/978)).

**A bar across the top**: *Stock*, the loaded railroad's name, what is unsaved,
and the one **Save**. It says *Everything is saved*, *<n> unsaved changes*,
*Saved* for a moment after a Save lands, or the refusal standing: a field's,
Save's own (the length guard, a train with nothing in it, nothing loaded), or
the store's.

**Two columns below it**: the list, `minmax(300px, 380px)`, and the editor of
the item chosen in it. Where the view is narrower than 760 px — its own width,
read with a container query — it is one column: the list, and pressing a card
stands the editor in its place, with a back button.

**The list** has three tabs, **Trains · Cars · Models**, each with its count, a
*New train* / *New car* / *New model* button, and one card per item: a photo
frame 10:3 wide, the name, and a line of facts. A model: kind, scale, length,
*decoder*. A car: its model's name, its address, *camera*. A train: how many
cars, its length, its kind, its priority. A car's card shows its model's photo
and a train's its first locomotive's. **Every photo is shown whole**
(`object-fit: contain`): train cars are wide and low, and a crop cuts off the
end that tells two apart.

**Cars are few because they are yours.** A locomotive you own, with its
address, written once and never restated. **Models are what anything is made
of**, and ten identical hoppers are one card rather than ten
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

**The train's editor is its older controls** until
[#980](https://github.com/rails49/control/issues/980) draws its own: a train's
name, unmake, derived line and entries, with every car and model listed under
it beside a `+` that puts it at the tail.

## What it does

**Adding a model entry** to a train gives an **anonymous item**: the entry
names the model, and there is nothing else to say about it.

**Filling in an address or a camera promotes it to a car** in the Cars list,
named from the model with a suffix you can edit — `arnold-ce68-1` until you
call it `krokodil-a`. Nothing asks you to classify an item before you add it:
an address is the physical identity, and having one is exactly what puts an
item on `cars` (ADR-0061). A camera riding in the item is as much its own, so
it promotes the entry the same way, and the new car has the camera and no
address. Two locomotives of one product get two cars and two
addresses, written once, and neither is restated the next time a rake is made
up.

**A car can exist in no train**: a locomotive you own and have not made up a
rake for. Unmaking a train leaves its cars on the roster — composing a train
and owning the stock are two things.

**The `+` buttons name one train, and it is always a train there is.** They
are in the train's editor, and put a car or a model at the tail of the train
**chosen** — the card last pressed, or the train last made up. Unmaking that
train chooses the first train left; unmaking the last leaves nothing to add to,
and the editor says *Nothing here yet. Press New train.* **Renaming that train
carries the choice with it**: you renamed the train you were composing, not
another one ([#416](https://github.com/rails49/control/issues/416)).

Which train is chosen is held as a **name**, and a name is not a hold on the
train: the roster can stop having it. So it is resolved against the roster
wherever it is read and falls back to the first train there — one rule, rather
than a move written at each press that can take the train away
([#445](https://github.com/rails49/control/issues/445)).

**Names take any character** — `Ae 6/6`, `Re 4/4 II`, `S 1/S 2` — a model's, a
car's and a train's alike. None is a topic level or a path unencoded: a
model's key is minted and hidden (below), and `GET /picture/<railroad>/<train>`
percent-encodes the train. An empty name is refused: *A car needs a name.*,
*A train needs a name.*

**Kind never implies an address.** A powered van is a real thing
(`layout/interface.py`), so the address field is offered on every entry and
never assumed from what the model is.

**A car's camera sits under its address**, in the car editor and on each
entry row: where the camera riding in that car answers on the LAN, a host name or an
IPv4 address with no scheme, port, path or login — how the camera is spoken to
is the `camera` app's
([ADR-0082](../adr/0082-the-camera-cars-picture-is-relayed-by-the-camera-app.md)).
On an entry naming a car it sets that car's camera. Emptying the field takes
the camera off and keeps the car. Anything else is refused with *'cam:8080' is
not a camera address — write the camera's host name or IP address*, and a
camera another car carries with *car 'van-1' already carries camera 'cam-1'*:
one camera in two cars would put one picture on two trains, which the store
refuses as well (`lib/stock.py`). It reaches the store on Save, in the whole
`PUT /rosters/<railroad>`, and the length guard does not hold it: it moves
nothing the dispatcher fits.

**Composing a train and placing it are two actions**
([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)): a rake is durable
and lives in the roster; where it stands belongs to the run. You make it up
here and put it on the layout in the run view.

**Save writes the roster whole.** `PUT /rosters/<railroad>` is the document, so
a car left out is a car removed and removing one needs no verb. The store
validates it against the catalogue and writes nothing where it does not
validate, so a refusal arrives in the validator's own words and is shown on the
screen that caused it. An edit made while Save is writing stays an edit for
the next Save ([#723](https://github.com/rails49/control/issues/723)).

**A train with nothing in it cannot be saved.** Making one up and pressing
Save is the order of work this screen invites, so the screen refuses that save
itself, before the `PUT`, naming the train: *train 'ore' has nothing in it —
press + beside a car or a model, or remove it*. The store refuses the same
document — an empty `cars` list names no cars (`lib/stock.py`) — so a roster
it takes is always one `/rosters/<railroad>/trains` can answer, and the roster
on disk is unchanged either way. Save stays enabled: there is still something
to give the store once the train is filled
([#412](https://github.com/rails49/control/issues/412)). A hand-edited file can
say the same train the other way — naming neither `cars` nor a length — and the
store refuses that in the same words, so the screen catches it in the same
sentence: the guard reads a train with nothing in it rather than the key it is
written with ([#447](https://github.com/rails49/control/issues/447)).

**A roster written before [#223](https://github.com/rails49/control/issues/223)
opens here.** Such a file states a train's length and names no cars, and the
store keeps that shape legal for a person's own older file and answers it as
written (`lib/stock.py`, `_train`). The train is drawn as a row with that
length, nothing in it, no kind and no functions — the derivations answer for
what is not there, as `tc49.lib.roster.Train` does for the same document — and
a note in the row says it states its length and names no cars. **Composing it
converts it**: the first thing put in it drops the stated number, and the
length is the sum of its cars from then on, a train saying one of the two and
never both. Saving the roster unedited keeps the stated length as it was
([#414](https://github.com/rails49/control/issues/414)).

The note says what that costs before the press: it names the stated number and
says that filling the train in takes it. Emptying the train again does not
bring it back — the train is the ordinary shape by then, and an empty one is
refused at Save ([#412](https://github.com/rails49/control/issues/412)). The
stated length is a property of the older shape that the conversion consumes,
so the screen owes the price before the press rather than the number
afterwards ([#448](https://github.com/rails49/control/issues/448)).

**Unsaved roster edits refuse what would discard them.** The railroad is the
app's and both its documents go with it, so a load in the settings dialog and
a restore are refused while either is unsaved, in words naming which document
is at stake: *the drawing*, *the roster*, or *the drawing and the roster*
(#703, #733). A railroad arriving on `tc49/layout/state/railroad` is **not**
refused: it is what the apps are running, not a press of this page's, and the
page follows it (#371, ADR-0060); a row naming `""` is no railroad, and this
view holds none for it. A rake composed and not saved used to go with no
trace, the guard reading only the drawing
([#415](https://github.com/rails49/control/issues/415)). The words are
the loaded railroad's, as the documents are: `ui/src/model/railroad.ts` holds
the `Stock` and the filing both, says which of them holds edits, and the app
hands the dialogs what to refuse over (#758). **Switching view
changes no railroad**, so nothing is read again and the rake comes back as it
was left. Closing or reloading the browser is not refused; neither is the
drawing.

**A refused edit puts the field back.** A refusal changes the document by
construction not at all, so the field is written back to what the document
holds while the words say why: rename a model to one another model has and the
name goes back to the one it had. It used to keep the typed value, so the screen
displayed a name, an address or a length nothing had (#416).

**The field an edit was typed into, and no other.** The write-back is the
render that edit asked for, and it names the field it came from. A frame about
the railroad is not news about what somebody is typing: this view redraws for
reasons that have nothing to do with the field being typed in — the app hands
it `placed`, and every new status the session answers replaces the run state
whole — and a person half way through correcting a length lost it to whoever
pressed GO on the panel ([#444](https://github.com/rails49/control/issues/444)).
A refusal on one field leaves an edit standing in another alone for the same
reason: what was not typed there was not refused.

**Refusals name what holds a thing.** A car a train is made of cannot be
removed: its Remove is dead, its title naming the train. A model's editor says what uses
it — the cars that are one, then the trains whose entries do — read there
rather than run into, and its Delete is dead while anything does.

**No session.** Like the editor, this is a document view, and the bus carries
nothing about what a railroad owns
([ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)).
**It reads no document itself.** The roster and the catalogue are read, held
and saved by the loaded railroad (`ui/src/model/railroad.ts`), which every view
shares, so no view can hold a railroad the row no longer names
([#758](https://github.com/rails49/control/issues/758)). What this screen
sends itself is a model's `DELETE` and a picture asked of the camera.

## The model editor

From the top, as the mockup draws it.

**The photo**, in a frame 10:3 wide, below.

**Name**: any characters. Refused when empty — *A model needs a name.* — or
when another model has it — *There is already a model 'Ae 6/6'.* — and the
field is put back. The store refuses a second model of one name too
(`AssetStore.put_model`). A document that states no name reads as its key.

**Kind**: Locomotive · Passenger · Freight · Special. **Scale**: a select of Z,
N, TT, H0, S, 0, 1, G (`lib.roster.SCALES`). **Length over buffers**, under
the length guard below. **Notes**: a textarea; emptied, the key goes from the
document.

**Decoder**: a switch. Turning it on with no functions adds F0 *Headlights*;
turning it off drops the functions, a function being a bit on a decoder and
the store refusing functions on a model without one (`lib/stock.py`).
**Functions**, while it is on: one row each — the number F0–F68, the name,
**Toggle · Hold** (`latching` · `momentary`, GLOSSARY.md **Function**) and a
remove. *Add a function* takes the lowest number not in use. A number listed
twice says *F2 is listed twice. One number names one function.* under the rows,
and Save is refused while it stands; so is a function with no name, *F1 needs
a name.* A latching function's document says nothing about its mode, absent
reading as latching.

**Used by**: the loaded railroad's cars of this model, then its trains with
entries naming it. **Delete model** is dead while the list is not empty.
Pressed, it asks *Delete <name>? Its photo goes with it. A backup can bring it
back.* and sends `DELETE /catalogue/<model>` at once
([#976](https://github.com/rails49/control/issues/976)). The store reads every
railroad's roster for it, so a model no car or train here uses can still be
refused for a railroad that is not loaded: that refusal is said under the
button in the store's words, and the model stays. A model made here and not
yet saved goes from the page alone; the store has never had it.

**New car**, at the top right, makes a car of this model, named after it —
*Ae 6/6*, then *Ae 6/6 (2)* — with no address, and shows it in the Cars list.
The Cars list's own New car asks *New car of which model?* first. Where the
model has a decoder, the car editor asks for the address at once (below).

## The car editor

From the top, as the mockup draws it
([#979](https://github.com/rails49/control/issues/979)).

**The model's photo**, read-only and marked *Photo of the model*: a car has no
photo of its own (ADR-0061).

**Name**: any characters. Refused when empty — *A car needs a name.* — or when
another car on the railroad has it — *There is already a car 'Re 460 001'.* —
and the field is put back. Renaming a car renames it in every train naming it.

**Model**: a button with the model's name that opens it in the Models list.

**The address**, the number programmed into the car's decoder, where the
model has a decoder or the car already has one. Committed when the field is
left, and written without leading zeros. Refused, the field put back, where it
is not a number from 1 to 10239, the field's words saying so, and where
another car has it: *Car Re 460 001 already has address 460.* — two cars on one
address both answer the same packet, which the store refuses too. Where the
model has no decoder and the car no address it says *<model> has no decoder.*
and offers *Fitted one to this car? Give it an address*, which shows the
field. Emptying the field takes the address off and keeps the car.

**Camera address**, always shown, under the address: as above, empty where
the car carries no camera.

**Different from the model.** *Length over buffers*, empty meaning the
model's, with the model's length as its placeholder and under the length
guard. **Functions**, where the model has a decoder or the car an address: the
model's shown as chips — number, name, *hold* on a momentary one — and *This
car's decoder is different: give it its own functions*, which copies them onto
the car as function rows edited as the model editor's are, Save refused the
same way while a number is listed twice or a function has no name. *Use the
model's functions again* takes the car's own off. **Notes**: the model's shown
above, read-only, and a textarea for the car's own `notes`, kept apart from
the model's ([#975](https://github.com/rails49/control/issues/975)); emptied,
the key goes.

**In trains**: each train whose entries name the car, as a link that opens it
in the Trains list.

**Remove**, at the top right, takes the car off the roster. It is dead while a
train holds the car, its title naming the train: *In train IC. Take it out of
the train first.*

**A new car of a model with a decoder is asked for its address at once**:
*Address for <car>* — *<model> has a decoder. Type the address programmed into
this car's decoder.* — with **Later**, which leaves it with none, and **Set
address**, refused in the field's words with the question left standing.

## Saving

**One Save**: each changed model's document with `PUT /catalogue/<model>`, then
each changed photo with `PUT /catalogue/<model>/photo` under `image/jpeg`,
then the roster with `PUT /rosters/<railroad>`. That is the order the store
takes them in: it refuses a photo of a model it has not got, and a roster
naming one, whole (`lib/stock.py`, [#630](https://github.com/rails49/control/issues/630)).
A refusal stops the Save where it happened, as
[#718](https://github.com/rails49/control/issues/718) has it: what was written
stays written, and what was not is still an edit for the next Save.

**A new model is written by Save**, no longer the moment it is made. *New
model* adds *New model* — *New model (2)* where that is taken — to the list,
chosen, with its name selected to be typed over: a passenger car in H0, 200 mm,
with no decoder. It is put in trains and given cars like any other before it is
saved, and the roster that names it is written after it.

**Its key is minted at that first write** from its name and never changes:
lower-cased, accents dropped (NFKD), every run of characters other than
`a–z0–9` turned into `-`, `-` trimmed from both ends, `model` if nothing is
left, then `-2`, `-3` … until no model has it. `Ae 6/6` is `ae-6-6`. The key
is the file's name and what every car names; it is never shown
([ADR-0023](../adr/0023-internal-names-are-minted-and-hidden.md)). Until that
write the model is held under a key no document can have, and the roster's
references move with it when it is minted.

## A model's photo

**Every card shows a photo** — an `<img>` on `GET /catalogue/<model>/photo`,
where one model's picture hangs below its document
([#630](https://github.com/rails49/control/issues/630)). Where that answers
anything but `200` the frame reads *No photo*: nothing on a model's document
says whether there is one, so an image that did not load is the whole of how
this screen learns there is none. **A car shows its model's photo**, and a
train its first locomotive's: the picture says what the product looks like,
and ten identical hoppers have one between them
([ADR-0061](../adr/0061-stock-with-nothing-of-its-own-is-named-by-its-model.md)).

**In the model editor, dropping an image file on the frame, at any time, makes
it the model's photo**; with none, the frame says *Drop a picture here*. Under
it, **Choose file…** — the browser's own `<input type="file"
accept="image/*">` — and **Take photo**, **Retake photo** where the model has
one.

**A dropped or chosen file is decoded by the browser and written again as a
JPEG at most 1600 px wide, quality 0.88, never cropped**, by `toJpeg` in
`ui/src/model/photo.ts`: a phone's photo is several megabytes and a frame
shows a fraction of that, and the store keeps a JPEG and nothing else. A file
that is not an image: *That file is not a picture.* One the browser cannot
decode — HEIC on most desktops: *This browser cannot read that picture. Try a
JPEG or PNG.* Either is said under the frame and changes nothing.

**Take photo fetches `GET /camera/snapshot`** and keeps the camera's bytes as
they are. That route is a **photo camera's and the store never answers it**:
on a box its own stack claims `/camera`, while in development vite proxies the
prefix to the port a photo camera listens on ([SYSTEM.md](../SYSTEM.md),
[DEPLOY.md](../DEPLOY.md), [#629](https://github.com/rails49/control/issues/629)).
While the camera is waited on the frame reads *Taking a picture…* and the press
is dead. **Any status but `200` means no picture** — there is nothing else for
a caller to read out of it — and is said under the frame as *no picture:*
followed by the status and its text, or by what the fetch said, with the press
live again: a camera plugged in a minute later is a picture a minute later.

**A photo chosen, dropped or taken is the page's until Save writes it**, shown
in the frame and on the card meanwhile and counted among the unsaved changes.
Once written the card asks for `?v=<n>`, because the bytes at that URL have
changed and the browser is holding the ones from before; the store drops a
query string, so it is the same route (#630). A photo the store refuses stays
on the page for the next Save.

**A photo is the model's and never the car's.** An item with a photo of its own
would be a second kind of picture to keep, and what a person is telling apart
on this screen is products ([#628](https://github.com/rails49/control/issues/628)).

## The length guard

A length lives on the **model** as well as on the **car** — `stock._car` takes
`model.length` unless the car overrides it — so correcting a product's length
changes every item of that product, including the one under a train the
dispatcher is fitting into blocks right now.

So **length editing is disabled while track power is on or draining**, with the
reason said on the control: the field keeps its box, takes the hint colour, and
carries `track power is on — turn it off to correct a length` both as its title
and beside it. A field that vanished would leave a person looking for it. With
power off, a length can be corrected whether or not a train is placed
([ADR-0071](../adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)).

It is **disabled as well while the page has not heard which railroad is
loaded** and still holds a roster, titled `the layout has not said whether the
track has power, so a length cannot be corrected`. A page that has lost the
broker keeps the roster it was editing, but cannot know whether the track has
power: its link can drop while the broker, `layout` and the dispatcher go on
running trains by the lengths they hold. The guard keys on the row naming the
railroad and not on power reading nothing, which a joined page whose drawing
is invalid also reads, and whose lengths stay editable. Nothing is
latched: once the row is heard again with power off, lengths are editable
(#804).

A correction is an edit to the page, and reaches the store on the roster's
**Save**. While power is on or draining, **Save is disabled if the unsaved edits
change a length**, titled `a length has changed — turn track power off to save`:
the layout builds only with power off, so a length saved then could not be
built. While the row naming the railroad is not heard it is disabled for the
same edits, titled `a length has changed — the layout has not said whether the
track has power`. Other roster edits save as before. **A save that changed a length names
the loaded railroad again** on `tc49/layout/railroad_wanted`, so the dispatcher
fits trains with the new length; a train now longer than its block comes off
the layout and is listed as **unfit**. A save pressed while the broker was up
that lands after it has gone owes the request: it is sent once the broker is back, the row names the
same railroad and power reads off, and dropped if the row names another
railroad or none (#803).

A **model** corrected in its editor is written by that Save too, with
`PUT /catalogue/<model>`, before the roster: each changed model once, as it
then stands, then the roster
([#718](https://github.com/rails49/control/issues/718)). A refusal stops the
Save where it happened and is said in the bar. A model already written stays
written; what was not written is still an edit, and the next Save writes it. If
a model was written before the refusal, the railroad is named again all the
same: power is off, and the dispatcher must not go on fitting trains by a length
the store no longer holds. A model correction names the railroad again whether
or not the loaded roster uses that model; a model written for its name, notes
or functions alone names nothing, moving no length.

**A model made here and not yet saved is outside the guard.** No train the
dispatcher fits is made of a model the store has not got, so its length is
editable with power on and is no length edit: making a product during a run
does not hold the Save.

This is a **UI guard in one browser**. `tc-app.ts` holds the run state — track
power, and which trains the session says are placed — and passes it down, the
same path the throttle's cabs take. A second browser editing stock during a run
is not covered, and the store enforces none of it (ADR-0071).

## With nothing loaded to write into

This view is one of the app's views of the loaded railroad (ADR-0038), and
nothing is loaded until the broker names a railroad
([ADR-0060](../adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
Until then there is no roster and no catalogue, and **the presses that write
are dead with the reason on them** — the New buttons and Save: *load a
railroad first* where none has been named, and *the roster and the catalogue
are not read yet* where one has and its read has not landed. The bar says the
same, or which of the three ways that read failed, below.

New model was once the press left open: on a box with an empty store its
dialog opened, every field took input, and Create did nothing at all — no
document written, no refusal shown, no request out of the browser
([#565](https://github.com/rails49/control/issues/565)). So **a press on this
screen either does what it says or says why it cannot**. New train says its
reason before it asks for a name rather than after; a prompt cancelled or left
empty stays a person's own no, as it is everywhere in the app.

## When the store does not answer with a document

A read or a write fails in **three ways, and the words say which**
([#411](https://github.com/rails49/control/issues/411)). *Nothing answered* —
`fetch` rejects, the connection refused — is *the store is not answering — run
`tc49 serve`*. *An answer that is not the store's* — a status with a body that
is not JSON, which is what a proxy's own 404 page or a 502 from one whose
upstream is down looks like from here — says what was asked and what came back:
*GET /catalogue answered 404*, with the status text where the browser gives
one. It guesses at no cause; this screen does not know there is a proxy. *The
store's refusal* is the validator's own words, as above. Which of the three it
was is decided once in `ui/src/model/store.ts`, and this screen shows the
result rather than a message of its own: it used to name `tc49 serve` for all
three, and told a person to start a store that was up and answering
([#405](https://github.com/rails49/control/issues/405)).

**The read is made again after the first two**, on `RETRY_MS`, argued in
`ui/src/model/store.ts` — and the message goes when a read lands. Both are
things to wait out: the store starting, or whatever is in front of it learning
where it is. A refusal is not, the store having answered, and nothing is read
again after one. There is nothing on this screen to press, so without the try
the message stood until somebody reloaded the page. The try is the loaded
railroad's, one timer for the drawing, the roster and the trains, made whichever
view is current, and dropped when the row names another railroad. So is what
was being composed: a roster edited for the railroad that was open goes when
another is loaded, the app having asked about it first (#415). A Save still in
flight then writes its answer onto nothing the new railroad shows (#758).

**A Save that did not land leaves everything it did not write**, with the
message in the bar — *PUT /catalogue/hopper answered 404* — so a model made
here, its photo and the roster naming it are all still there to write again
once the store is reachable.

## The run view beside it

**The trains are read again when the run view becomes the current view.** The
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

The fields are the browser's own `input`, `select` and `textarea`, and the
questions Delete and a new car's address ask are look's `look-dialog`, the way the properties dialog
is. The view's layout, the bar, the tabs and the cards follow the mockup; its
colours are the app's palette.

`ui/src/model/stock.ts` holds the edits Save writes: each changed model, each
photo waiting, and the function rows a document keyed by number cannot hold
while a number is listed twice. `ui/src/model/railroad.ts` mints the keys and
writes them in the store's order. A model's `DELETE` is `ui/src/model/store.ts`'s,
beside the routes the rest of this screen reads, as are where a model's photo
is, saving one, and taking a picture. The last of those is not a store call and
is the only call in the app that is not, which is why what it does with a
status is its own: a `200` is the picture and anything else is none.
`ui/src/model/photo.ts` is the one conversion of a picture file into the JPEG
the store keeps. A picture waiting to be saved is held as a `data:` URL rather
than an object URL — an object URL is a handle that has to be given back, and
a model whose picture is chosen three times would leak two. In development `ui/vite.config.ts` proxies `/camera`
to a photo camera the way it proxies the store's prefixes, so the page fetches both on its own
origin.

The view is not in the shell's left-pane slot. `--pane` is the width of the
strip beside a drawing surface — the editor's palette, the run view's roster
([#169](https://github.com/rails49/control/issues/169)) — and this view has no
surface, so it declares its own columns and leaves `--pane` alone. It puts
no commands on the rail either: `RAIL.stock` is empty, there being no viewport
to move, and a `Save` there would be a second Save meaning something other than
the one beside it. The views are the whole of this view's rail
([ADR-0064](../adr/0064-the-chrome-is-a-band-and-a-rail.md)).

Its entry in `VIEWS` in `ui/src/model/views.ts` names its glyph,
`train-freight-front`, so the wagon on the rail's selector is part of this
rather than something to remember
([ADR-0073](../adr/0073-the-chrome-comes-from-look.md)).

## Tests

Split the way the app's suites are split. `ui/test/composing.test.ts` drives
the model with no DOM — promotion and the name it mints, the derived length,
kind and functions, two locomotives of one product, what holds a car or a
model, the length guard, and the model editor's rules: New model's names, the
key minted from a name and kept, a name refused, the decoder and its function
rows with their mode, a number listed twice stopping Save, a photo held for
Save; and the car editor's: an address out of 1 to 10239 or another car's
refused, a car's own notes, and its own functions copied from the model,
stopping Save while one has no name, and taken off again. `ui/test/railroad.test.ts` has Save write a model made here, its photo
and the roster, in that order and under the key minted.

`ui/test/making.test.ts` mounts the app in this view against a store with no
`catalogue/` and no roster — and, for the older shape, against one answering a
train that states its length — and drives the controls: the bar's words, a
model written by Save and not before, a model named `Ae 6/6` saved under
`ae-6-6`, a duplicate name refused and put back, the decoder switch and the
function rows reaching the document with `mode`, a duplicate function number
refusing Save, Delete dead while the model is used, asking and sending
`DELETE` where it is not, and the store's refusal under it; the car editor —
a second car of a decoder model asked for its address and refusing the first
car's, an address refused and put back, a camera address set, refused and
emptied, a length override written and removed by emptying it, the car's own
functions written and removed, its notes reaching the roster document, Remove
dead while a train holds the car, and its links to its model and its trains; a car named
`Re 4/4 II` and a train named `S 1/S 2` saved; a train made up of a locomotive
and three hoppers, the document that reaches `PUT /rosters/<railroad>` with one
car entry and three model entries, the guard killing a field while track power
is on, Save waiting for power off when a length changed and then naming the
railroad again, a corrected model written before the roster and kept for the
next Save where it is refused, the run view showing a train made up here
without a reload, the row an older roster's train draws and the first entry
converting it, the chosen train moving when the one it named is unmade and
carried when that one is renamed, the field a refusal puts back, the edit
standing in a field that a frame about the railroad leaves alone, the presses
that write being dead with nothing loaded (#565), and the three ways a call to
the store fails as this screen shows them. The words themselves are
`ui/test/asking.test.ts`'s, at the helper that decides them.

`ui/test/photos.test.ts` mounts the same app against a camera, with
`toJpeg` replaced: the photo route a model's, a car's and a train's card show,
*No photo* where it did not load, a dropped and a chosen file reaching
`PUT /catalogue/<model>/photo` as the conversion's output under `image/jpeg`
on Save, a file that is no picture and one the browser cannot read refused in
words, the frame while the camera is waited on and the dead press with it, the
camera's own bytes on Save, what a `502` reads as, a model made with a photo
written as the document, the photo and the roster under the key minted, and a
photo the store refused kept for the next Save. What the camera answers is the
shell's (`ui/test/support/shell.ts`, `camera`), that route being a photo
camera's and no app of this repository's.

The question over unsaved roster edits is `ui/test/opening.test.ts`'s, beside
the drawing's: it is the app's question about the app's railroad, and what the
two documents have to say about it belongs in one place (#415).
