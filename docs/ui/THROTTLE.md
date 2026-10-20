# Throttle view

The view a person drives trains from: take a train, drive it, give it back,
take it back ([#207](https://github.com/rails49/control/issues/207),
[#208](https://github.com/rails49/control/issues/208)). It is one of the app's
views of the loaded railroad, the [run view](PANEL.md) and the
[editor](EDITOR.md) being the others
([ADR-0038](../adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)), and
its commands ride the bus like everything else — the gestures
`tc49/layout/take_wanted`, `tc49/layout/throttle_wanted` and
`tc49/layout/throttle_alive`, which are rows of the inventory marked
browser-writable and are answered by `layout`
([ADR-0035](../adr/0035-a-topic-has-one-writing-role.md), BUS.md). They are
gestures because there are any number of throttles, two tabs being two of
them, while the device row a throttle's speed ends at has one writer,
`layout` ([#263](https://github.com/rails49/control/issues/263)).
Terminology follows [CONTEXT.md](../../CONTEXT.md), **Throttle** and
**Throttle** and **Driving mode**
([ADR-0079](../adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).

## What it shows

The view is **the train picker while this page's throttle holds no train**,
and **a column of driving controls for each train it holds** while it holds
any ([#853](https://github.com/rails49/control/issues/853),
[#855](https://github.com/rails49/control/issues/855)). A train is not picked
without being taken: the columns are the trains `tc49/layout/state/taken`
names this throttle for. All of them are held under the page's one throttle
id; there is no id per column.

**The columns**, side by side where the view is wide enough. The width is the
view's own, read with a `ResizeObserver`, not the window's. A train's column is
at least 360 px wide, the take column 260 px, and the gap 14 px, so
`columns(width)` (`ui/src/model/throttle.ts`) is `floor((width − 260) / 374)`,
at least 0 — 0 at 390 px, 1 at 820, 2 at 1180, 4 at 1920.

- **No train held**: the picker fills the view at any width.
- **`columns(width)` is 0**, a phone: no take column. Each held train's
  controls stand one below the other, and the first carries the clock.
- **`columns(width)` is 1 or more**: that many trains' columns side by side,
  then the take column. Held trains beyond them go on a further row, and the
  view scrolls.
- **Nothing is released or hidden because the view narrowed.**
- **The order** is the one in which `state/taken` first named this throttle for
  each train, kept by the view for the life of the page. A new train's column
  goes after the others; a released train's column goes and the others keep
  their order.

**The take column**, on the right: the page's one clock at the top, then
*Take another train* and the picker drawn `compact` — the same cards by the
same rules, as rows of thumbnail, name and where. While this page holds
`columns(width)` trains or more, the list is replaced by *no room for another
train — release one*.

**The picker** is headed *Take a train*, with one card for each train the
railroad has placed (`tc49/dispatch/state/allocation`) that this throttle does
not hold, by name. Placement is the whole of the rule: a train off the layout
has nothing for a throttle to move
([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)), and putting one on
is the run view's pane. Nothing else about the layout appears here — no
drawing, no route, no block colours. With no train placed it says *no train is
on the layout — place one in the run view*.

A card shows a thumbnail, the train's name, and where it stands: its block, or
*crossing a transit*. The thumbnail is the model photo of the train's first
locomotive, from the catalogue (`/catalogue/<model>/photo`), by the model the
roster route names (`locomotive`, `GET /rosters/<railroad>/trains`); the
train's name stands in its place where the train has no locomotive, the roster
does not have it, or the photo does not load. The cards are a grid, two across
on a 390 px phone and more where the view is wider, and every press on them is
at least 44 px high.

- **A train no throttle holds** has **Take**.
- **A train another throttle holds**, another tab on the same device included,
  is drawn faded and says *held by another throttle*. It has no Take, because
  `layout` would drop one, and has **Force release**.
- **The last train this throttle held** (*Take back*, below), while it is placed
  and no throttle holds it, comes first and apart from the grid, says *You held
  this one* above its name, and has **Take back**.

**Each held train's column**, laid out as arrangement A at every width
([#852](https://github.com/rails49/control/issues/852)), for that train only:

- **At the top, the train's picture**: the same photo as its card, or its
  name — the thumbnail — and, where the train carries a camera, the camera
  car's live picture over it (below). Over that: the train's name, the
  aspect, the block it stands in or *crossing a transit*, the blocks ahead,
  and Release.
- **Below, on the left**: the reverser, the train's functions, Turn around and,
  on a phone's first column only, the clock.
- **Below, on the right**: the speed, the slider and STOP, where a right thumb
  holding a phone is.

**The aspect at the end the reverser points the train to**, from
`tc49/dispatch/state/aspects`: for Forward the end its facing names
(`tc49/schedule/state/facing`, CONTEXT.md, **Facing**), for Reverse the
block's other end. A person driving by hand reads the signal, and this is
where they read it — the view derives no aspect, exactly as the panel derives
none ([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
The blocks the train's committed route has past the one it stands in wear the
two colours a route is lit in on the run view: green where the dispatcher
holds the lock and the train may move, cyan where the route is chosen and the
claim has not been made yet. Neither is derived here either; both are read off
the same ledger the picture is lit from ([PANEL.md](PANEL.md)).

**The speed** as a whole percentage of the train's maximum, with no sign, and
under it *at rest*, *nose first* or *tail first*.

**The clock**, `tc-clock`: the browser's local wall time as a station clock —
a white face, twelve black bars, black hour and minute hands and a red second
hand, redrawn once a second. The page has one: at the top of the take column,
or on a phone in the first held train's column. It stays wall time until the
railroad has a fast clock.

**Nothing about hardware.** No address, no decoder step, no command station,
no function number. The UI reaches the bus and the store and there is no other
world for it ([#208](https://github.com/rails49/control/issues/208)). A
throttle that talked to a command station would be a different program in a
different repository, and this one is not that.

## What it does

**The throttle mints its id.** When the page opens, the session picks a
random string and names the throttle by it on every frame that concerns a
train it holds: `tc49/layout/take_wanted` `{train, throttle}` to take a train,
with `null` to release it, `throttle` on `tc49/layout/throttle_wanted`, and
`tc49/layout/throttle_alive` `{throttle}` once a second while it holds a
train. The id names the throttle holding a train, not who sent a frame. At most
one throttle holds a train, `layout` says which on `tc49/layout/state/taken`,
and it releases the trains of a throttle it has not heard for 5 s by default,
set per installation ([DEPLOY.md](../DEPLOY.md#a-silent-throttle)), so a phone
gone to sleep does not leave a train running
([ADR-0079](../adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md),
BUS.md). Reloading the page mints a new id, and the trains the old one held
are released once its silence runs out.

**What `layout` does with them** (docs/layout/README.md, *Who drives*). The
railroad is in one driving mode, `manual` or `automatic`, stated on
`tc49/layout/state/driving`; the band's driving control shows it and switches
it in this view too ([PANEL.md](PANEL.md)). A take of a train another throttle holds is
dropped. The speed is applied from the throttle holding the train at any time,
granted move or not, while the rails are live: the move ending at its sensor
writes `0.0`, and the next speed frame drives the train on. A frame reversing a
running train writes `0.0` until the throttle sends `0` (ADR-0084). A train no
throttle holds stands at its signal in `manual` and is driven on its grant in
`automatic`. So a release writes `0.0` in `manual`; in `automatic` mid-move it
writes nothing and the train keeps the person's speed until the move ends, or
the grant's speed where the train stands (ADR-0081, ADR-0083); in `automatic`
with no move outstanding, `0.0`.

**Taking a train** — Take or Take back on its card — publishes one
`take_wanted` naming the train and this throttle's id. The gesture names who should hold the train rather than asking
for a change, so a second take by the throttle already holding it is not a
race, and `layout` counts it as hearing from that throttle.

**The train reads as taken when the state topic says so**, never on the
gesture. `layout` holds who holds each train and publishes `state/taken`, and a
view that marked a train taken on its own press would show a person holding a
train `layout` never handed them (ADR-0035). So the picker stays after Take
until `state/taken` names this throttle for the train, and a take `layout`
drops changes nothing on screen. The driving controls show while `state/taken`
names this throttle for the train and at no other time: after Release the view
goes back to the picker once the row no longer names it, with that train first
as Take back. `throttle_alive` follows the same row: it starts when
`state/taken` names this throttle for a train on the layout and stops when it
names it for none, or the broker goes.

**A train another throttle holds** cannot be taken from here. Its **Force
release** publishes `take_wanted` with `null` — the same frame as a release,
which frees the train whoever holds it. Once `state/taken` no longer names a
throttle for it, it is a free card with Take.

**Take back.** The last train is the train `state/taken` most recently named
this throttle for. It is kept whatever ended the hold — this page's Release,
the release timeout, or a force release from elsewhere — and changes only when
`state/taken` names this throttle for another train. The session keeps it in
the tab's `sessionStorage` under `tc49.throttle.last.<railroad>`, written when
it changes and read when the session joins a railroad, so a second app opened
in the same tab finds it. Where storage throws, the session keeps it in memory
for the life of the page. A reload mints a new throttle id, so a train the old
page held shows as held by another throttle until its silence runs out, and
then as Take back.

The release writes **one frame and no speed of its own**. `layout` decides what
a release is worth on the rails — `0.0` in `manual`; in `automatic` mid-move,
the speed the person left, or the grant's where the train stands (SYSTEM.md,
*Who drives*); a zero from here would be a second party deciding how fast the
railroad drives it.

**The slider is live whenever this throttle holds the train** and the rails
are live, granted move or not
([ADR-0081](../adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)):
a person at a platform can back a train up a few centimetres without asking
for a move. It runs from 0 at the bottom to 1 at the top in steps of 0.05, and
dragging it does not scroll the page. Leaving the block is the person's
responsibility; nothing stops a held train at its block's ends.

**The reverser** is two presses, Forward and Reverse, both shown and the
current one pressed (CONTEXT.md, **Reverser**). Forward drives the train nose
first, Reverse tail first; it turns neither the facing nor any car. It is live
under the slider's conditions **and only with the slider at 0**
([ADR-0084](../adr/0084-a-reverser-moves-only-with-the-lever-at-0.md)): a flip
at speed reverses a rolling train, and behind a long one cars can leave the
rails. Switching it sends nothing; the next slider input carries the new
sign. It is Forward on every take.

**The speed is one signed number for the train.** Each slider input publishes
one `tc49/layout/throttle_wanted` `{train, speed}`: the slider's value, signed
by the reverser — Forward positive, Reverse negative — as a fraction of that
train's maximum. `+` is the way the train points, not a locomotive's own
forward. `layout` composes the sign each car's decoder is given from the
direction the speed states and the way round that car is coupled
([ADR-0045](../adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)),
so a person driving a top-and-tail set moves one slider and both locomotives
do the right thing. Which locomotive a speed reaches is never this view's
question ([#292](https://github.com/rails49/control/issues/292)).

**The slider goes to 0, sending nothing**, when the train's granted move ends
(`layout` writes `0.0` at the move's sensor), when the train is released by
anybody, when a train is taken, when the run takes the train off the layout,
and when `state/power` reads `off`. The reverser keeps its position through
all of these except a take. A train released in `automatic` mid-move keeps the
person's speed until the move ends, `layout`'s decision and not this view's;
the slider here is at 0 because this throttle no longer drives it.

The move is read off the retained `state/allocation` picture and not worked
out from the locks: the train is in its `crossing` — the dispatcher's own
outstanding set, written at the grant and dropped at the arrival sensor — and
one of its requests carries a `route`, the move behind it. A frame that leaves
a train with no move, where it had none before, ends nothing and leaves the
slider where it was.

What is on screen is what went on the bus: the slider publishes the value it
is now showing, and the percentage above it is that value.

**STOP is one gesture.** It puts the slider to 0 and publishes `0`, and leaves
the reverser where it is, because it is the control a person reaches for when
something is wrong and sliding back through every speed between is not that.

**Turn it round.** A control publishing `tc49/schedule/reversal_wanted`,
`{train}` — the same gesture the run view's right-click menu writes — offered
**only while the slider is at zero**: flipping the facing under a moving train
would reverse it on the spot. It is greyed while that train has a request in
flight, which is the run view's own rule about the same flip and is here for
the same reason: the request departs the end the facing named when it was
composed, so a flip under it leaves the train pointing one way and leaving the
other ([#295](https://github.com/rails49/control/issues/295)). After a flip the
same reverser drives the train the other way physically, which is the point
of working in the train's frame.

**The functions** of the train's own cars, by the names the catalogue gives
them and by no number, from `GET /rosters/<railroad>/trains` — a train's functions
are derived from its cars, name by name, the first car declaring one being the
one that stands (ADR-0045). A name is the whole of what a function is: it is
one bit on the wire, so there is no value list to draw a chooser from
([ADR-0063](../adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)). A train whose cars declare none shows none,
which is most of the stock a railroad owns.

The first two always show. With three or more, a `>>` follows them; pressing
it shows the rest below, in the same order, and pressing it again hides them.
It is closed whenever a train is taken.

**Each button shows what `layout` says**: on or off is read from
`tc49/layout/state/functions`, which maps train to function name to boolean
([#849](https://github.com/rails49/control/issues/849)). A name the row does
not give for the train reads off, and so does every function before the row
is heard or where its payload cannot be read. A button that is on has
`aria-pressed="true"`.

**A press asks**: one `tc49/layout/function_wanted` `{train, throttle,
function, on}` naming this page's throttle id, the function's name, and `on`
the opposite of what the button shows. The button changes only when
`state/functions` does. `layout` writes the device row,
`tc49/layout/state/wanted/function/<addr>/<number>`, of the first car in the
train's order that has an address and declares the name (BUS.md, *Device
vocabulary*). Every function latches: one press on, the next off.

The buttons are live while `state/taken` names this throttle for the train
and nothing below refuses a gesture, whether or not a move is outstanding.
Otherwise they are drawn with their state and dead, and a press sends
nothing.

**Everything is dead while the rails are not live.** With
`tc49/layout/state/power` anything but `on`, or with no session answering, no
gesture can be sent from this view and the reason stands where the controls
are, on the picker and on the cab, as `STILL` in `ui/src/model/throttle.ts` has them: *the railroad is
draining — switch it on to drive* and *the track has no power — switch it on
to drive*, or *no broker answering — is the bus running?* with no session
answering
([ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md),
ADR-0078). Take, Take back and Force release publish nothing then, like every
control on the cab. Reading what each train is and what it faces goes on
working: reading is not gesturing.

**Every width.** The picker is full width, from a phone to a desktop, and the
columns fill the view as *The columns* above lay them out; there is no side
pane. A view too short for them scrolls.

**Each column acts on its own train.** STOP publishes `throttle_wanted`
`{train, speed: 0, throttle}` for that column's train only, Release
`take_wanted` `{train, throttle: null}` for it only, and the slider, the
reverser and Turn around act on it only. The column goes when `state/taken` no
longer names this throttle for the train. There is no STOP for every held train
at once: the band's power is the railroad's stop.

## What it is not

**Not a mode of the system.** A train a throttle holds is dispatched like any other: it
holds its block, it is granted moves, and it moves only on a route the
dispatcher allocated, with a person trusted to read the signal this view
shows them. The dispatcher never reads who holds a train (ADR-0079).

**Not a hand-held throttle.** What such a thing needs is exactly the four
gesture topics, which are contract and not this view's
([DEPLOY.md](../DEPLOY.md)). Consisting, decoder programming and a train that
is not on the layout are all somewhere else.

## Implementation

`ui/src/ui/tc-throttle.ts`, a Lit component in the shape the other views take,
with its styles beside it, which lays out the picker in
`ui/src/ui/tc-train-picker.ts`, one `ui/src/ui/tc-driving.ts` per held train —
each owning its own train's slider and reverser — and the clock in
`ui/src/ui/tc-clock.ts`. The picker sends `take-wanted` and
`release-wanted`, the train their detail, which the app carries to the
session's `pressTake` and `pressRelease`; a function button sends
`function-wanted` `{train, function, on}`, carried to `pressFunction`. Neither works anything out: every
train offered, who
holds each, whether it has a move outstanding, the end each points at, the
aspects at both ends of its block, the road ahead, the functions, its first
locomotive's model and whether it is the last train held arrive as `Cab`s from
`ui/src/model/throttle.ts`, which is a pure function over the apps' answers,
this page's throttle id and the last train held, and holds no state of its
own. The panel model
reads `state/taken`, `state/functions` and `state/allocation`
(`ui/src/model/panel.ts`).

**The session is the app's.** There is one socket per page, and the session
that holds it is the one that joined the railroad the app has loaded
(`ui/src/model/session.ts`, PANEL.md,
[#171](https://github.com/rails49/control/issues/171),
[#756](https://github.com/rails49/control/issues/756)). So the cabs are worked
out where the model and the roster already are and handed down by the app, and
this view's gestures go the same path the band's track-power presses take
(ADR-0074): the view asks, the app carries, the session writes. Two sockets on
one page would be two clients of one run, every frame applied twice. The
throttle id is the session's for the same reason, and so are the
`throttle_alive` timer and the last train held, which follow `state/taken`
whichever view is on screen.

**The screen stays awake while the page holds a train**
([#854](https://github.com/rails49/control/issues/854)), so a phone left lying
does not sleep, fall silent and have `layout` release the train (ADR-0079). The
page holds a train on the condition `throttle_alive` runs on — `state/taken`
names this page's throttle for a train on the layout — and while it does it
holds one screen wake lock (`navigator.wakeLock.request("screen")`) for any
number of trains: `ui/src/ui/wake.ts`, told by the app on every render and let
go of as the app leaves the page. Holding ending, however it ends — released
here or by Force release elsewhere, released by `layout` once its silence runs
out, the train taken off the layout, another railroad loaded, or the broker
gone — releases the lock, and a lock that arrives after holding ended is
released as it arrives. The browser drops the lock while the page is hidden,
and may drop it while it is shown; it is asked for again when the page is next
shown while holding, or when holding next starts. A browser with no wake lock,
or one that refuses, changes nothing else: no message, no retry loop.

What is this view's own is what belongs to the person at it: where they have
put each train's slider and reverser, and the order of the columns. None is on
the bus — nothing publishes a throttle's position back — so each slider is what
its column shows and, signed, what it last sent. When the run takes a train off
the layout its column goes, and with none left the view goes back to the
picker: there is nothing left for a slider to move.

**The camera car's picture** is an `<img class="picture">` on the `camera`
app's `GET /picture/<railroad>/<train>`, the loaded railroad's name and the
train's each URL-encoded, with a *LIVE* mark on it
([ADR-0082](../adr/0082-the-camera-cars-picture-is-relayed-by-the-camera-app.md),
[#857](https://github.com/rails49/control/issues/857)). It is drawn over the
thumbnail while all three hold: this view is the one on screen, `state/taken`
names this throttle for the train, and the trains route says the train carries
a camera. Track power does not matter. Otherwise it is not in the page at all,
so the page holds no connection to the route: a release by anybody, taking
another train, the train leaving the layout and switching to another view each
remove it. A stream that fails — an `error` on the element — removes it too,
and the thumbnail shows; while the three still hold it is put back after
`RETRY_MS` (`ui/src/model/store.ts`) under `?try=<n>`, so the browser makes a
new request, and again after each failure until a stream plays or one of the
three stops holding. A picture that stops changing while its connection stays
open is not noticed.

The **roster route** carries what a person can switch beside the length,
whether the train carries a camera, and the model of its first locomotive,
head first, or `null` where it has none (`GET /rosters/<railroad>/trains`,
`store/server.py`). All four are derived from the cars the train is made of
and none is authored, so they arrive together; the cars themselves, their
addresses, where a camera answers and which function number each name sits on
are the roster screen's and the translator's, never a view's. A model name is
not a decoder detail, so the first locomotive's is a view's to read.

## Tests

Split the way the app's suites are split. `ui/test/cabs.test.ts` drives the
model with no DOM — which throttle holds a train, here or elsewhere, an
unreadable entry leaving it held by nobody, the move outstanding read off the
picture from the grant to its sensor and none for a restored crossing with no
request behind it, the end it points at, the aspect there and at the block's
other end, the blocks ahead and their claims, the first locomotive's model or
`null` where the field is absent, a camera only where the route says `true`,
which trains are offered at all, the
last train held first, marked, only while it is placed and nobody holds it,
and a function on where `state/functions` gives it as on for the train and
off where the row does not name it, has not been heard or cannot be read.
`ui/test/session.test.ts` checks the frames the session writes — the take and
release under its id, the speed and a function press naming it — and the timing of
`throttle_alive` on a fake clock: once a second from the `state/taken` row
naming this throttle, never on the press, never for a train another throttle
holds, once a second and not once per train while it holds two, and stopping
when it holds nothing or the broker goes; and the last
train held, written to `sessionStorage` under `tc49.throttle.last.<railroad>`
when `state/taken` names this throttle, unchanged by a release, read back on
joining, and kept in memory where storage throws.
`ui/test/throttle.test.ts` mounts the app in this view and drives the
controls, which is the only place the questions this page is about can be
asked: that the picker has a card per placed train and no list, with the
locomotive's photo or the train's name, that Take writes one `take_wanted` and
not two, that the picker stays until `state/taken` names this throttle, that a
train another throttle holds is faded with no Take and is force released with
`null`, that a train held and freed comes back first as Take back — not while
another throttle holds it, not off the layout, found by a second app in the
same tab, not with `sessionStorage` cleared, and still there with storage
throwing — that the
slider drives a held train with no move outstanding and runs from 0, that the
reverser signs it, is dead off 0, sends nothing when switched and is Forward
on every take, that the slider goes to rest when a granted move ends and when
power reads off and stays put on a frame that ends no move, that the speed
reads as a percentage and which end leads, that STOP publishes zero and leaves
the reverser, that the aspect shown follows the reverser, that the picture is
the first locomotive's photo with the name standing in, that a train held
here with a camera shows the camera car's picture over it, and none for a
train with no camera, held elsewhere or held by nobody, that an `error` takes
the picture away until `RETRY_MS` on a fake clock puts it back under a new
`try`, but not once the train is released, that a release, taking another
train, the train leaving the layout and the run view each leave no picture,
that releasing writes
`null` and goes back to the picker with Take back, that a train with no
functions shows no button and no `>>`, one or two show with no `>>` and three
show two and `>>`, which opens the third, that a press on a held train, with
or without a move granted, writes one `function_wanted` asking for the
opposite of what the button shows while the button waits for
`state/functions`, that a press on a train held elsewhere or by nobody, with
power off or with no broker writes nothing, and that
with the rails dead every press leaves nothing on the socket at all — checked
by pressing them, not by trusting a disabled attribute.
With `ResizeObserver` stood in for to report the view's width, it checks that
at 1180 px two trains held stand in two columns in the order `state/taken`
first named this page for each, with one clock in the view; that STOP and the
slider in one column publish only that column's train, the other's reading
unchanged; that Release in one column writes one `null` `take_wanted` and the
column stays until `state/taken` drops the train, which the take column then
lists; that the take column lists the other placed trains where there is room
and says there is none, with no Take, once the columns are full, at 1180 px
holding two and at 820 px holding one; that at 390 px there is no take column;
that narrowing from 1180 px to 390 px publishes nothing and stacks both; and
that every frame naming a throttle names the same id.
`ui/test/columns.test.ts` checks `columns(width)` at 390, 820, 1180 and 1920 px.
`ui/test/clock.test.ts` puts the clock's hands at a fake time.
It also gives the app a fake `navigator.wakeLock`: `state/taken` naming this
throttle asks for the lock, naming another throttle or the broker closing lets
it go, and with no wake lock at all taking, driving and releasing write the
same frames. `ui/test/wake.test.ts` drives `ui/src/ui/wake.ts` with a lock and
a page as doubles: one request for any number of trains, the lock let go when
holding ends, including one that arrives late, asked for again when the page
is shown, not when the browser drops it while shown, and nothing thrown by a
browser with no lock or one that refuses.
