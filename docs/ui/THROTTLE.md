# Throttle view

The view a person drives a train from: pick a train, take it, drive it, give
it back ([#207](https://github.com/rails49/control/issues/207),
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

**The trains the railroad has placed**, from `tc49/dispatch/state/allocation`,
one row each in the left pane — the shell's one left-pane slot, where the
editor puts its palette and the run view its roster
([#169](https://github.com/rails49/control/issues/169)). Placement is the whole
of the rule: a train off the layout has nothing for a throttle to move
([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)), and putting one on
is the run view's pane. Nothing else about the layout appears here — no
drawing, no route, no block colours; this view is about one train.

A row says where the train stands, or *crossing a transit* where it stands in
no block, and carries **yours** where `tc49/layout/state/taken` says this
throttle holds it and **taken** where it names another. A train another tab
holds is marked too, because who holds a train is `layout`'s word about the
train and not about this page.

**What the picked train is.** Its name, the way it points, the aspect it is
reading and the blocks in front of it.

**The facing arrow** is the run view's, moved here as well as kept there: the
value is `tc49/schedule/state/facing`, the run the train would make across its
block, and the end that run comes out at is the end drawn beside the lever
(CONTEXT.md, **Facing**). It is here because it is what says which physical
direction `+` on the lever is, and a person wants that before they move it,
not after.

**The aspect at the end the train would leave by**, from
`tc49/dispatch/state/aspects`, and the blocks the train's committed route has
past the one it stands in. A person driving by hand reads the signal, and this
is where they read it — the view derives no aspect, exactly as the panel
derives none
([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
The blocks ahead wear the two colours a route is lit in on the run view: green
where the dispatcher holds the lock and the train may move, cyan where the
route is chosen and the claim has not been made yet. Neither is derived here
either; both are read off the same ledger the picture is lit from
([PANEL.md](PANEL.md)).

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
`tc49/layout/state/driving`. A take of a train another throttle holds is
dropped. The lever is applied from the throttle holding the train at any time,
granted move or not, while the rails are live: the move ending at its sensor
writes `0.0`, and the next lever frame drives the train on. A frame reversing a
running train writes `0.0` until the throttle sends `0` (ADR-0084). A train no
throttle holds stands at its signal in `manual` and is driven on its grant in
`automatic`. So a release writes `0.0` in `manual`; in `automatic` mid-move it
writes nothing and the train keeps the person's speed until the move ends, or
the grant's speed where the train stands (ADR-0081, ADR-0083); in `automatic`
with no move outstanding, `0.0`.

**Taking a train** publishes one `take_wanted` naming the train and this
throttle's id. The gesture names who should hold the train rather than asking
for a change, so a second take by the throttle already holding it is not a
race, and `layout` counts it as hearing from that throttle.

**The train reads as taken when the state topic says so**, never on the
gesture. `layout` holds who holds each train and publishes `state/taken`, and a
view that marked a train taken on its own press would show a person holding a
train `layout` never handed them (ADR-0035). The speed control is offered
while `state/taken` names this throttle for the train and at no other time, so
releasing takes it away. `throttle_alive` follows the same row: it starts when
`state/taken` names this throttle for a train on the layout and stops when it
names it for none, or the broker goes.

**A train another throttle holds** reads as taken and cannot be taken: the Take
is dead, because `layout` would drop it. Beside it stands **Force release**,
which publishes `take_wanted` with `null` — the same frame as a release, which
frees the train whoever holds it.

The release writes **one frame and no speed of its own**. `layout` decides what
a release is worth on the rails — `0.0` in `manual`; in `automatic` mid-move,
the speed the person left, or the grant's where the train stands (SYSTEM.md,
*Who drives*); a zero from here would be a second party deciding how fast the
railroad drives it.

**The lever is live only while the train has a move outstanding**: from the
grant to the `block_occupied` of the block that move enters, which is the span
`layout` applies a throttle's speed in. The span is read off the retained
`state/allocation` picture and not worked out from the locks: the train is in
its `crossing` — the dispatcher's own outstanding set, written at the grant
and dropped at the arrival sensor — and one of its requests carries a `route`,
the move behind it. The crossing the dispatcher restores after a restart has no
request behind it and no move `layout` is known to hold, so it leaves the lever
dead. Because the picture is retained, a page opened or reloaded mid-move sees
the lever as `layout` does. Outside a move it is dead and at rest, which is the
speed `layout` wrote when the move ended, and the view says the lever waits for
the next grant.

**The lever is one signed number for the train.** `tc49/layout/throttle_wanted`
carries `{train, speed}`, −1.0 through 0 to 1.0 as a fraction of that train's
maximum, and **`+` is the way the train points** — not a locomotive's own
forward. `layout` composes the sign each car's decoder is given from the
direction the lever states and the way round that car is coupled
([ADR-0045](../adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)),
so a person driving a top-and-tail set pushes one lever and both locomotives
do the right thing. Which locomotive a speed reaches is never this view's
question ([#292](https://github.com/rails49/control/issues/292)).

What is on screen is what went on the bus: the lever publishes the value it is
now showing, and the number beside it is that value.

**Centre is stop and is one gesture.** A STOP beside the lever centres it and
publishes `0`, live whether or not a move is outstanding, because it is the control a person reaches for when something
is wrong and sliding back through every speed between is not that.

**Turn it round.** A control publishing `tc49/schedule/reversal_wanted`,
`{train}` — the same gesture the run view's right-click menu writes — offered
**only while the lever is at zero**: flipping the facing under a moving train
would reverse it on the spot. It is greyed while that train has a request in
flight, which is the run view's own rule about the same flip and is here for
the same reason: the request departs the end the facing named when it was
composed, so a flip under it leaves the train pointing one way and leaving the
other ([#295](https://github.com/rails49/control/issues/295)). After a flip the
same lever drives the train the other way physically, which is the point of
working in the train's frame.

**The functions** of the train's own cars, by the names the catalogue gives
them and by no number, from `GET /rosters/<railroad>/trains` — a train's functions
are derived from its cars, name by name, the first car declaring one being the
one that stands (ADR-0045). A name is the whole of what a function is: it is
one bit on the wire, so there is no value list to draw a chooser from
([ADR-0063](../adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)). A train whose cars declare none shows none,
which is most of the stock a railroad owns.

They are **drawn and not yet live**. A function reaches a decoder through the
device vocabulary, `tc49/layout/state/wanted/function/<addr>/<number>`, whose
one writer is `layout` (BUS.md, *Device vocabulary*), and no gesture
carrying a function press is declared — the rows a throttle rides on are
the take and the speed
([#296](https://github.com/rails49/control/issues/296),
[#297](https://github.com/rails49/control/issues/297)). Drawing them is what
says a train has them; the day the gesture is declared, this is the view it is
sent from, and nothing else here changes.

**Everything is dead while the rails are not live.** With
`tc49/layout/state/power` anything but `on`, or with no session answering, no
gesture can be sent from this view and the reason stands where the controls
are: *emergency stop — clear it before driving* against *the track has no
power — switch it on to drive*, because the two ask for different actions by
the person recovering
([ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
Picking a train and reading what it faces go on working: reading is not
gesturing.

## What it is not

**Not a mode of the system.** A train a throttle holds is dispatched like any other: it
holds its block, it is granted moves, and it moves only on a route the
dispatcher allocated, with a person trusted to read the signal this view
shows them. The dispatcher never reads who holds a train (ADR-0079).

**Not a hand-held throttle.** What such a thing needs is exactly the three
gesture topics, which are contract and not this view's
([DEPLOY.md](../DEPLOY.md)). Consisting, decoder programming and a train that
is not on the layout are all somewhere else.

## Implementation

`ui/src/ui/tc-throttle.ts`, a Lit component in the shape the other views take,
with its styles beside it. It works nothing out: every train it offers, who
holds each, whether it has a move outstanding, the end each points at, the
aspect there, the road ahead and the functions arrive as `Cab`s from
`ui/src/model/throttle.ts`, which is a pure function over the apps' answers
and this page's throttle id, and holds no state of its own. The panel model
reads `state/taken` and `state/allocation` (`ui/src/model/panel.ts`).

**The session is the app's.** There is one socket per page, and the session
that holds it is the one that joined the railroad the app has loaded
(`ui/src/model/session.ts`, PANEL.md,
[#171](https://github.com/rails49/control/issues/171),
[#756](https://github.com/rails49/control/issues/756)). So the cabs are worked
out where the model and the roster already are and handed down by the app, and
this view's gestures go the same path the band's track-power presses take
(ADR-0074): the view asks, the app carries, the session writes. Two sockets on
one page would be two clients of one run, every frame applied twice. The
throttle id is the session's for the same reason, and so is the
`throttle_alive` timer, which runs off `state/taken` whichever view is on
screen.

What is this view's own is what belongs to the person at it: the train they
picked and where they have put the lever. Neither is on the bus — nothing
publishes a throttle's position back — so the lever is what this view shows
and what it last sent. It returns to rest when the train is picked afresh,
when the train is given back by anybody, when its move ends, and when the run takes the train off
the layout, which also lets go of the train entirely: there is nothing left
for a lever to move.

The **roster route** carries what a person can switch beside the length
(`GET /rosters/<railroad>/trains`, `store/server.py`). Both are derived from the cars
the train is made of and neither is authored, so they arrive together; the
cars themselves, their addresses and which function number each name sits on are
the roster screen's and the translator's, never a view's.

## Tests

Split the way the app's suites are split. `ui/test/cabs.test.ts` drives the
model with no DOM — which throttle holds a train, here or elsewhere, an
unreadable entry leaving it held by nobody, the move outstanding read off the
picture from the grant to its sensor and none for a restored crossing with no
request behind it, the end it points at, the aspect there, the blocks ahead
and their claims, and which trains are offered at all.
`ui/test/session.test.ts` checks the frames the session writes — the take and
release under its id, the speed naming it — and the timing of
`throttle_alive` on a fake clock: once a second from the `state/taken` row
naming this throttle, never on the press, never for a train another throttle
holds, and stopping when it holds nothing or the broker goes.
`ui/test/throttle.test.ts` mounts the app in this view and drives the
controls, which is the only place the questions this page is about can be
asked: that taking a train writes one `take_wanted` and not two, that the view
waits for `state/taken` before it says a train is taken, that a train another
throttle holds cannot be taken and is force released with `null`, that the
lever is dead until a move is granted and goes to rest when it ends, that the
number on screen is the number that went out, that centring publishes zero,
that releasing writes `null` and takes the lever away, and that with the rails
dead every press leaves nothing on the socket at all — checked by pressing
them, not by trusting a disabled attribute.
