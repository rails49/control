# Throttle view

The view a person drives trains from: take a train, drive it, give it back
([#207](https://github.com/rails49/control/issues/207),
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
Terminology follows [GLOSSARY.md](../../GLOSSARY.md), **Throttle** and
**Throttle** and **Driving mode**
([ADR-0079](../adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md),
[ADR-0089](../adr/0089-a-throttle-holds-one-train.md)). Visual reference:
[throttle-mockup.html](images/throttle-mockup.html).

## What it shows

The view is **a row of throttles**
([#966](https://github.com/rails49/control/issues/966)). Each throttle is a
panel the size of a phone screen with its own throttle id, and holds at most
one train. A panel is **the train selector while its throttle holds no train**
([#853](https://github.com/rails49/control/issues/853),
[#967](https://github.com/rails49/control/issues/967)), and **that train's
driving controls** while it holds one, with the selector opened over the whole
panel by pressing the train's picture. A train is not picked without being
taken: a panel drives the train `tc49/layout/state/taken` names its throttle
for.

**The panels.** The width is the view's own, read with a `ResizeObserver`, not
the window's. `panels(width)` (`ui/src/model/throttle.ts`) lays them out:

- **`width` ≤ 440 px**, a phone: one panel exactly `width` wide, with no margin
  and no gap.
- **Wider**: the content width is `w = width − 16` (8 px each side), the count
  `max(1, floor((w + 20) / 380))`, and each panel
  `min(440, floor((w − 20 × (count − 1)) / count))` wide, 20 px apart, the row
  centred — two of 361 px at 758, two of 440 at 1118, five of 364 at 1920.
- **A panel's height** is the view's, less 16 px where it is not a phone,
  clamped to 560–834 px (`panelHeight`). Panels are top-aligned, and the view
  scrolls where they do not fit.

**Which panels.** The view keeps an ordered list of panel slots, starting at
`0 … count − 1`; each slot is one throttle id. When the count grows, the lowest
slots not shown go on the end. When it shrinks, panels holding no train go,
from the end, until the list is the count long. A panel holding a train is
never dropped: it wraps onto a further row. **Nothing is released because the
view narrowed**, and a resize publishes nothing.

**The selector** is headed *Choose a train*, with *<n> trains on the layout*
under it, and one card for each train the railroad has placed
(`tc49/dispatch/state/allocation`), by name. Placement is the whole of the
rule: a train off the layout has nothing for a throttle to move
([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)), and putting one on
is the run view's pane. Nothing else about the layout appears here — no
drawing, no route, no block colours. With no train placed it says *no train is
on the layout — place one in the run view*. While the panel holds a train the
header has a 40 px close button (✕) on the right, which closes the selector and
writes nothing; a panel holding none always shows the selector, and has none.

A card shows a 16:9 thumbnail, the train's name, and where it stands: *at
<block>*, or *crossing a transit*. The thumbnail is the model photo of the
train's first locomotive, from the catalogue (`/catalogue/<model>/photo`), by
the model the roster route names (`locomotive`, `GET
/rosters/<railroad>/trains`); the train's name stands in its place where the
train has no locomotive, the roster does not have it, or the photo does not
load. The cards are a grid two across, and **every card is a press**:

- **The panel's own train** is outlined and says *driving here*. Pressing it
  closes the selector.
- **A train no throttle holds**: pressing it takes it — where the panel holds a
  train, `take_wanted` with `null` for that train first, then the take, in
  that order (a throttle holds one train, ADR-0089).
- **A train another throttle holds**, another panel on this page and another
  tab on the same device included, is faded and says *held by another
  throttle*. Pressing it asks first, in a dialog inside the panel: *Take
  <name>?* — *Another throttle is driving this train. Taking it releases it
  there first. In manual driving the train stops before it is yours.* —
  with *Cancel*, which writes nothing, and *Take train*, which writes — where
  the panel holds a train — `take_wanted` with `null` for that train first,
  then `null` for the chosen train, then the take, in that order.
  There is no Force release: confirming a take is the same release frame.

The selector's bottom row is one full-width, 48 px **Release <name>**, which
writes `take_wanted` with `null` for the panel's train, and is disabled while
the panel holds none. **The selector closes when `state/taken` names the
panel's throttle for the train chosen in it**, never on the press: if a third
throttle takes the train between the release and the take, `layout` drops the
take and the selector stays open.

**A panel's driving controls**, for that train only, laid out as
[throttle-mockup.html](images/throttle-mockup.html) draws them, the same
layout at every panel width, 360–440 px
([#968](https://github.com/rails49/control/issues/968), ADR-0089):

- **At the top, the train's picture**: the panel's full width, 16:9, with no
  margin on any side, and pressing it opens the selector. It is the camera car's
  live picture once a frame has come (below), otherwise the first
  locomotive's photo — the same as its card — otherwise a train icon with the
  train's name under it, each shown whole
  ([#956](https://github.com/rails49/control/issues/956)) and centred, the
  space it leaves in the page's colour
  ([#1020](https://github.com/rails49/control/issues/1020)). Laid over it: the
  train's name in a small dark chip at the bottom left (not on the icon,
  which has it already), *LIVE* at the top left while the camera picture
  shows, a *Trains* chip at the top right saying the picture opens the
  selector, and the train's addresses at the bottom right, `#12 #47`, head
  first, on the icon too and not at all where no car has one
  ([#1033](https://github.com/rails49/control/issues/1033)).
- **Below it, two columns**: the left `minmax(0, 1fr)`, the right
  `clamp(104px, 30%, 136px)`, with a 12 px gap and padding.
- **Left, at the top**: the clock in the first row, the blocks in the second,
  and the signal beside both. Under them **the functions**.
- **Right**: the speed, the reverser's way under it, the slider filling the
  height left, and one 64 px button under the slider, where a right thumb
  holding a phone is.

**The blocks** are three rows, each a small upper-case label and a block name
in a monospace pill: *at* the block the train stands in, or *crossing a
transit* while it stands in none; *next* the first block of its committed
route past the one it stands in; *to* the last, the same block as *next* where
there is one. *Next* and *to* wear the two colours a route is lit in on the run
view: green where the dispatcher holds the lock and the train may move, cyan
where the route is chosen and the claim has not been made yet. With no route
ahead both read *—*. Neither colour is derived here; both are read off the
same ledger the picture is lit from ([PANEL.md](PANEL.md)).

**The signal** is an SBB system L main signal over its distant signal, as
FDV R 300.2 figs 519, 524 and 528 draw them, 50 × 156 px
([ADR-0094](../adr/0094-caution-is-warnung-the-panel-draws-system-n-and-the-throttle-system-l.md)). The main signal has two
lamps, green above red; the distant signal is a square head under it with
four, amber top left and top right, green middle right and bottom left.
*Stop* lights the main red with the distant signal dark, *caution* (Warnung)
the main green and both ambers, *clear* the main green and both greens, and
no aspect lights nothing. The panel draws the same aspect as system N, one
lamp ([EDITOR.md](EDITOR.md#symbol-geometry)). The aspect is the one at the end the reverser points the train
to, from `tc49/dispatch/state/aspects`: for Forward the end its facing names
(`tc49/schedule/state/facing`, GLOSSARY.md, **Facing**), for Reverse the
block's other end. A person driving by hand reads the signal, and this is
where they read it — the view derives no aspect, exactly as the panel derives
none ([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
The housing is near-black and its rim follows the theme; the lamps keep their
colours in either.

**The speed** as a whole percentage of the train's maximum, 36 px, with no
sign, and under it ▶ *Forward* or ◀ *Reverse*, the way the reverser is set.

**The theme** is the page's: every colour comes from the palette and follows
the system's light or dark setting. The clock and the signal are pictures of
things on a railroad and keep their own colours; what is laid over the train's
picture is light on a dark chip in either.

**The clock**, `tc-clock`: the railroad's fast clock as a station clock —
a white face, twelve black bars, and black hour and minute hands. It has no
second hand: sped up, one sweeps too fast to read
([#1031](https://github.com/rails49/control/issues/1031)). Every panel
holding a train has one. It draws what `tc49/layout/state/clock` last said and
reads no clock of the browser's, so it moves when the row does, once a real
second. With no railroad loaded or no broker answering it draws its face with
no hands
([ADR-0090](../adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).

**Nothing about hardware but the addresses.** No decoder step, no command
station, no function number. The UI reaches the bus and the store and there
is no other world for it ([#208](https://github.com/rails49/control/issues/208)).
A throttle that talked to a command station would be a different program in a
different repository, and this one is not that. It shows a train's addresses,
so a person can drive the train from another throttle, and never writes one
([#1033](https://github.com/rails49/control/issues/1033)).

## What it does

**Each throttle mints its id.** The session picks a random string for each
panel slot the first time the view asks for it (`throttleFor(slot)`), keeps it
for the life of the page, and names the panel's throttle by it on every frame
that concerns the train it holds: `tc49/layout/take_wanted` `{train, throttle}`
to take a train, with `null` to release it, `throttle` on
`tc49/layout/throttle_wanted` and `tc49/layout/function_wanted`, and
`tc49/layout/throttle_alive` `{throttle}` once a second for each id
`state/taken` names for a train on the layout. The id names the throttle holding a train, not who sent a frame. At most
one throttle holds a train, `layout` says which on `tc49/layout/state/taken`,
and it releases the trains of a throttle it has not heard for 5 s by default,
set per installation ([DEPLOY.md](../DEPLOY.md#a-silent-throttle)), so a phone
gone to sleep does not leave a train running
([ADR-0079](../adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md),
BUS.md). Reloading the page mints new ids, and the trains the old ones held
are released once their silence runs out.

**What `layout` does with them** (docs/layout/README.md, *Who drives*). The
railroad is in one driving mode, `manual` or `automatic`, stated on
`tc49/layout/state/driving`; the band's driving control shows it and switches
it in this view too ([PANEL.md](PANEL.md)). A take of a train another throttle holds is
dropped. The speed is applied from the throttle holding the train at any time,
granted move or not, while the rails are live: the move ending at its sensor
writes `0.0`, and the next speed frame drives the train on. A frame reversing a
running train writes `0.0` until the throttle sends `0` or `layout` stops the
train itself (ADR-0084, ADR-0088). A train no
throttle holds stands at its signal in `manual` and is driven on its grant in
`automatic`. So a release writes `0.0` in `manual`; in `automatic` mid-move it
writes nothing and the train keeps the person's speed until the move ends, or
the grant's speed where the train stands (ADR-0081, ADR-0083); in `automatic`
with no move outstanding, `0.0`.

**Taking a train** — its card pressed — publishes one `take_wanted` naming the
train and the id of the panel it was pressed in. The gesture names who should hold the train rather than asking
for a change, so a second take by the throttle already holding it is not a
race, and `layout` counts it as hearing from that throttle.

**The train reads as taken when the state topic says so**, never on the
gesture. `layout` holds who holds each train and publishes `state/taken`, and a
view that marked a train taken on its own press would show a person holding a
train `layout` never handed them (ADR-0035). So the panel's selector stays
after the press until `state/taken` names the panel's throttle for the train,
and a take `layout` drops changes nothing on screen. The driving controls show
while `state/taken` names the panel's throttle for the train and at no other
time: after Release the panel shows the selector alone once the row no longer
names it. `throttle_alive` follows the same row: each tick sends one frame for each
of this page's ids `state/taken` names for a train on the layout, and none
while it names none, or the broker goes.

**A train another throttle holds** is taken only once a person confirms it.
*Take train* publishes, where the panel holds a train, `take_wanted` with
`null` for that train first — a throttle holds one train (ADR-0089), and
`layout` does not refuse a second take by the same id — then `take_wanted` with
`null` for the chosen train — the same frame as a release, which frees the
train whoever holds it — and then the take. `layout`'s rule that a take of a
held train is dropped stays, which is why the release goes first.

The release writes **one frame and no speed of its own**. `layout` decides what
a release is worth on the rails — `0.0` in `manual`; in `automatic` mid-move,
the speed the person left, or the grant's where the train stands (SYSTEM.md,
*Who drives*); a zero from here would be a second party deciding how fast the
railroad drives it.

**The slider is live whenever the panel's throttle holds the train** and the rails
are live, granted move or not
([ADR-0081](../adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)):
a person at a platform can back a train up a few centimetres without asking
for a move. It runs from 0 at the bottom to 1 at the top in steps of 0.01, with
21 tick marks every 5 % that get longer toward the top, those at or below the
value in the accent colour. **Dragging the blue handle moves the value by the
distance the finger travels** over the track's usable height, so a touch on
the handle moves nothing. **A press anywhere else on the grey puts the handle
under the finger** and publishes that value, and a drag from there follows
the finger (#996); a press above or below the handle's travel is 1 or 0. No
drag scrolls the page. The arrow keys move it 0.01, PageUp and PageDown 0.1.
Leaving the block is the person's responsibility; nothing stops a held train
at its block's ends.

**The button under the slider** is the stop and the reverser, by where the
slider stands, since the reverser moves only with the slider at 0
([ADR-0084](../adr/0084-a-reverser-moves-only-with-the-lever-at-0.md)):

- **Above 0**, a white square on red: the stop. One press puts the slider to 0
  and publishes `0`, and leaves the reverser where it is, because it is the
  control a person reaches for when something is wrong and sliding back
  through every speed between is not that.
- **At 0**, ▶ with the reverser at Forward and ◀ at Reverse: a press flips the
  reverser (GLOSSARY.md, **Reverser**) and sends nothing; the next slider
  input carries the new sign. Forward drives the train nose first, Reverse
  tail first; it turns neither the facing nor any car. A flip at speed would
  reverse a rolling train, and behind a long one cars can leave the rails,
  which is why it is offered only here. It is Forward on every take.

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
the slider here is at 0 because the panel's throttle no longer drives it.

The move is read off the retained `state/allocation` picture and not worked
out from the locks: the train is in its `crossing` — the dispatcher's own
outstanding set, written at the grant and dropped at the arrival sensor — and
one of its requests carries a `route`, the move behind it. A frame that leaves
a train with no move, where it had none before, ends nothing and leaves the
slider where it was.

What is on screen is what went on the bus: the slider publishes the value it
is now showing, and the percentage above it is that value.

**The throttle does not turn a train round.** Facing is the scheduler's, set
where requests are composed, in the run view's menu
(`tc49/schedule/reversal_wanted`, ADR-0089). The same reverser drives a train
the other way physically, which is the point of working in the train's frame.

**The functions** of the train's own cars, by the names the catalogue gives
them and by no number, from `GET /rosters/<railroad>/trains` — a train's functions
are derived from its cars, name by name, the first car declaring one being the
one that stands (ADR-0045). A name is the whole of what a function is: it is
one bit on the wire, so there is no value list to draw a chooser from
([ADR-0063](../adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)). A train whose cars declare none shows none,
which is most of the stock a railroad owns.

All of them show, two across, every button at least 50 px high, in the left
column under the blocks. They run down the left column first and then down
the right, the left taking the odd one
([#1031](https://github.com/rails49/control/issues/1031)). Where they do not
fit, the function area scrolls and nothing else does.

**Each button shows what `layout` says**: on or off is read from
`tc49/layout/state/functions`, which maps train to function name to boolean
([#849](https://github.com/rails49/control/issues/849)). A name the row does
not give for the train reads off, and so does every function before the row
is heard or where its payload cannot be read. A button that is on has
`aria-pressed="true"`.

**A press asks**: a `tc49/layout/function_wanted` `{train, throttle,
function, on}` naming the panel's throttle id and the function's name. The
button changes only when `state/functions` does. `layout` writes the device
row, `tc49/layout/state/wanted/function/<addr>/<number>`, of the first car in
the train's order that has an address and declares the name (BUS.md, *Device
vocabulary*). What a press asks for is the function's mode, as
`GET /rosters/<railroad>/trains` gives it, and a function it gives no mode
for is latching ([#981](https://github.com/rails49/control/issues/981)):

- **A latching function**: one press sends one `function_wanted` with `on`
  the opposite of what the button shows — one press on, the next off.
- **A momentary function**, such as a horn: `on: true` as the pointer goes
  down on the button, and `on: false` at its `pointerup`, `pointercancel` or
  `lostpointercapture`. The button captures the pointer, so a finger sliding
  off still ends the hold. Space or Enter held on the focused button does the
  same with its key down and up, the key's repeat ignored. A hold also ends
  as the button loses focus (`blur`), as the page is hidden
  (`visibilitychange` to `hidden`, every hold on the panel) and as the panel
  is removed (every hold on the panel), since no key or pointer coming up
  reaches it then. Each hold sends one off, however many of its ends arrive,
  and sends it over dead rails too and whatever the panel holds by then:
  `layout` takes it at any power and drops it where this throttle no longer
  holds the train (BUS.md, `function_wanted`). A horn held as the band's stop
  is pressed is let go of, and does not sound again when power comes back
  ([#994](https://github.com/rails49/control/issues/994)). Only the start of
  a hold is refused where a press is.

A momentary button looks the same as a latching one, apart from its pressed
state, which is `state/functions`'s as every button's is.

The buttons are live while `state/taken` names the panel's throttle for the train
and nothing below refuses a gesture, whether or not a move is outstanding.
Otherwise they are drawn with their state and dead, and a press sends
nothing.

**Everything is dead while the rails are not live.** With
`tc49/layout/state/power` anything but `on`, or with no session answering, no
gesture can be sent from this view and the reason stands where the controls
are, on the selector, as a line under its header, and on the driving controls,
in a box over the bottom of the area below the picture, with the functions and
the slider column dimmed and the blocks, the clock and the signal still
readable, as `STILL` in `ui/src/model/throttle.ts` has them: *the railroad is
draining — switch it on to drive* and *the track has no power — switch it on
to drive*, or *no broker answering — is the bus running?* with no session
answering
([ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md),
ADR-0078). The cards, *Take train* and Release publish nothing then, like
every control on the cab, the end of a momentary function's hold apart: they are drawn dead with `aria-disabled` and stay
pressable, so the press reaches the guard that sends nothing. Reading what each train is and what it faces goes on
working: reading is not gesturing.

**Each panel acts on its own train.** The stop publishes `throttle_wanted`
`{train, speed: 0, throttle}` for that panel's train under its id only, Release
`take_wanted` `{train, throttle: null}` for it only, and the slider and the
reverser act on it only. The panel shows the selector alone when
`state/taken` no longer names its throttle for the train. There is no stop for
every held train at once: the band's power is the railroad's stop.

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
with its styles beside it, which lays out the panels, each holding the
selector in `ui/src/ui/tc-train-picker.ts` or one `ui/src/ui/tc-driving.ts` —
owning its own train's slider and reverser — with the clock in
`ui/src/ui/tc-clock.ts`, and the selector over it while it is open. The app
hands the view the session's `throttleFor`, and each panel hands its id to
what it holds. The picture sends `selector-wanted` and the close button
`selector-closed`, both to the panel and neither to the app; the panel notes
the train of each `take-wanted` its selector sends, and closes the selector
once `state/taken` names its throttle for that train. The selector sends
`take-wanted` `{train, throttle}`, carried to the session's `pressTake`, and
`release-wanted`, the train its detail, carried to `pressRelease`; the slider sends `throttle-wanted` `{train,
speed, throttle}`, carried to `pressThrottle`, and a function button
`function-wanted` `{train, throttle, function, on}`, carried to
`pressFunction`. Neither works anything out: every train offered, the id of the
throttle holding each (`Cab.holder`), whether it has a move outstanding, the
end each points at, the aspects at both ends of its block, the road ahead, the
functions and its first locomotive's model arrive as `Cab`s from
`ui/src/model/throttle.ts`, which is a pure function over the apps' answers,
compares no ids, and holds no state of its own. A panel compares `cab.holder`
with its own id. The panel model
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
throttle ids are the session's for the same reason, and so is the
`throttle_alive` timer, which follows `state/taken` whichever view is on
screen.

**The screen stays awake while the page holds a train**
([#854](https://github.com/rails49/control/issues/854)), so a phone left lying
does not sleep, fall silent and have `layout` release the train (ADR-0079). The
page holds a train on the condition `throttle_alive` runs on — `state/taken`
names an id this page minted for a train on the layout (`Session.ours`) — and
while it does it holds one screen wake lock
(`navigator.wakeLock.request("screen")`) for any number of throttles: `ui/src/ui/wake.ts`, told by the app on every render and let
go of as the app leaves the page. Holding ending, however it ends — released
here or by a take confirmed elsewhere, released by `layout` once its silence runs
out, the train taken off the layout, another railroad loaded, or the broker
gone — releases the lock, and a lock that arrives after holding ended is
released as it arrives. The browser drops the lock while the page is hidden,
and may drop it while it is shown; it is asked for again when the page is next
shown while holding, or when holding next starts. A browser with no wake lock,
or one that refuses, changes nothing else: no message, no retry loop.

What is this view's own is what belongs to the person at it: where they have
put each train's slider and reverser, and which panel slots are shown. None is
on the bus — nothing publishes a throttle's position back — so each slider is
what its panel shows and, signed, what it last sent. When the run takes a train
off the layout its panel shows the selector alone: there is nothing left for a
slider to move.

**The camera car's picture** is read with `fetch` from the `camera` app's
`GET /picture/<railroad>/<train>`, the loaded railroad's name and the train's
each URL-encoded, and each JPEG in the stream is drawn as an
`<img class="picture">` with a *LIVE* chip on it
([ADR-0082](../adr/0082-the-camera-cars-picture-is-relayed-by-the-camera-app.md),
[#857](https://github.com/rails49/control/issues/857),
`ui/src/model/picture.ts`). It is read while all three hold: this view is the
one on screen, `state/taken` names the panel's throttle for the train, and the trains
route says the train carries a camera. Track power does not matter. Otherwise
the read is aborted and the picture is not in the page: a release by anybody,
taking another train, the train leaving the layout and switching to another
view each end it. Until the first frame comes the thumbnail shows alone.

The page reads the stream rather than giving the route to an `<img>`, because
an image fires no `error` once its first frame is in: a stream that ends, or
stays open and sends nothing, would leave the last frame up under *LIVE*
([#950](https://github.com/rails49/control/issues/950)). An answer other than
200, a failed connection, the stream ending, and no frame for `STALL_MS` each
take the picture away and the thumbnail shows; while the three still hold it
is asked for again after `RETRY_MS` (`ui/src/model/store.ts`) under
`?try=<n>`, and again after each failure until a stream plays or one of the
three stops holding.

The **roster route** carries what a person can switch beside the length,
whether the train carries a camera, the model of its first locomotive, head
first, or `null` where it has none, and its cars' addresses, head first
(`GET /rosters/<railroad>/trains`, `store/server.py`). All five are derived
from the cars the train is made of and none is authored, so they arrive
together; the cars themselves, where a camera answers and which function
number each name sits on are the roster screen's and the translator's, never
a view's. A model name is not a decoder detail, so the first locomotive's is a
view's to read; the addresses are a view's to show and never to write
([#1032](https://github.com/rails49/control/issues/1032)).

## Tests

Split the way the app's suites are split. `ui/test/cabs.test.ts` drives the
model with no DOM — the id of the throttle holding a train, an unreadable
entry leaving it held by nobody, the move outstanding read off the
picture from the grant to its sensor and none for a restored crossing with no
request behind it, the end it points at, the aspect there and at the block's
other end, the blocks ahead and their claims, the first locomotive's model or
`null` where the field is absent, a camera only where the route says `true`,
which trains are offered at all, and a function on where `state/functions` gives it as on for the train and
off where the row does not name it, has not been heard or cannot be read.
`ui/test/session.test.ts` checks the ids — `throttleFor(0)` the same twice and
not `throttleFor(1)` — the frames the session writes — the take, the speed and
a function press naming the id they were pressed with, the release `null` —
and the timing of `throttle_alive` on a fake clock: once a second from the
`state/taken` row naming an id, never on the press, never for a train another
throttle holds, one frame for each id each tick where the row names two of
this page's, an id the row drops going quiet while the other goes on, and
stopping when it names none or the broker goes.
`ui/test/throttle.test.ts` mounts the app in this view and drives the
controls, which is the only place the questions this page is about can be
asked: that the selector has a card per placed train and no list, with the
locomotive's photo or the train's name, that a card writes one `take_wanted`
and not two, that the selector stays until `state/taken` names the panel's
throttle, that a train another throttle holds is faded with no Force release
and opens a dialog that writes nothing, *Cancel* nothing and *Take train*
`null` then the take, or in a panel holding a train `null` for that train
first, that the picture opens the selector with a close button
that writes nothing, that the panel's own card closes it, that a free card in a
panel holding a train writes `null` for that train then the take, that the
selector closes only when `state/taken` names the panel's id for the train and
stays open when a third throttle has it, that Release writes one `null` and is
disabled with no train, that the
slider drives a held train with no move outstanding and runs from 0, that a
drag of the handle moves it by the distance dragged in steps of 0.01 and a
touch on it publishes nothing, that a press on the grey publishes the value
there, a drag from it follows the finger, and above and below the travel is 1
and 0, that it stops at 0 and 1 and moves 0.01 on the arrows and 0.1 on
PageUp and PageDown, that it goes to rest when a granted move ends and when
power reads off and stays put on a frame that ends no move, that 21 marks
light up to the value, that the speed reads as a percentage and which way the
reverser is set, that the button under the slider publishes 0 above 0 and
leaves the reverser and at 0 flips the reverser, publishes nothing and signs
the next slider input the other way, and is Forward on every take, that the
signal has two main lamps, green over red, and four distant lamps, that
`caution` lights the main green and both ambers, `clear` the main green and
both greens and `stop` the main red and no distant lamp, read off `aspect` at
Forward and `tailAspect` at Reverse, and nothing with no aspect, that *at*, *next* and
*to* read `C2`, `CE2`, `A2` for a cab in `C2` with `CE2, X, A2` ahead, *at*
reads *crossing a transit* with no block and *next* and *to* *—* with nothing
ahead, that the picture is the first locomotive's photo with the name over it
and *Trains*, and the icon with the name under it and no name chip where it
has none, that there is no Turn around and no `pressReversal`, that a train held
here with a camera shows each frame of the camera car's picture in its place once
one comes, and asks for none for a train with no camera, held elsewhere or held
by nobody, that the stream ending, failing, answering other than 200 or
sending nothing for `STALL_MS` takes the picture away until `RETRY_MS` on a
fake clock asks again under a new `try`, but not once the train is released,
that a release, taking another train, the train leaving the layout and the run
view each abort the read and leave no picture, that releasing writes
`null` and shows the selector alone, that a train with no
functions shows no button, and five show all five with no `>>`, that a press on a held train, with
or without a move granted, writes one `function_wanted` asking for the
opposite of what the button shows while the button waits for
`state/functions`, that a press on a train held elsewhere or by nobody, with
power off or with no broker writes nothing, and that
with the rails dead every press leaves nothing on the socket at all — checked
by pressing them, not by trusting a disabled attribute. A momentary function
held sends one `on: false` when the pointer goes up after the rails went dead,
when its button loses focus with the key still down, when the page is hidden
and when the panel is removed.
With `ResizeObserver` stood in for to report the view's size, it checks that
at 758 px there are two selectors, a card in the second writing `take_wanted` under
slot 1's id and the first's card for that train then faded, *held by another
throttle* and opening the dialog when pressed; that each panel is as tall as the view less the margin; that
narrowing 758 → 390 px with only the second holding leaves that one and writes
nothing, and with both holding keeps both, one below the other; that widening
again adds an empty panel under another id; that every panel holding a train
has its own clock and its slider names its own id; that a train's controls, slider
and reverser survive a width change; and that at 390 px there is one panel,
exactly 390 px wide.
`ui/test/columns.test.ts` checks `panels(width)` at 360, 440, 758, 1118 and
1920 px, and `panelHeight`.
`ui/test/clock.test.ts` puts the clock's hands at a fake time.
It also gives the app a fake `navigator.wakeLock`: `state/taken` naming one of
this page's throttles asks for the lock, naming another throttle or the broker closing lets
it go, and with no wake lock at all taking, driving and releasing write the
same frames. `ui/test/wake.test.ts` drives `ui/src/ui/wake.ts` with a lock and
a page as doubles: one request for any number of trains, the lock let go when
holding ends, including one that arrives late, asked for again when the page
is shown, not when the browser drops it while shown, and nothing thrown by a
browser with no lock or one that refuses.
