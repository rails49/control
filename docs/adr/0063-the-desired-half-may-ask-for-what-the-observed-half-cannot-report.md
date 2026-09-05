# The desired half may ask for what the observed half cannot report

Resolves [#466](https://github.com/rails49/control/issues/466). Amends
[ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md):
its claim that a command station reached over JSON reports power as on or off
only, and its picture of a translator configured with nothing but a
connection. Amends [SYSTEM.md](../SYSTEM.md#layout-interface): `state/power`
is no longer folded from what the hardware reports alone.

The device vocabulary was checked row by row against the two paths that exist
— a command station's own protocol, and JMRI's JSON servlet, which reaches
every railroad JMRI drives and is therefore the wider test. The mapping is
[docs/layout/DEVICES.md](../layout/DEVICES.md); this records what the check
changed.

Nine of the ten rows survived the check unaltered in meaning. That is the
first result and it is worth stating: the vocabulary was written without
naming hardware, and it turns out to be carryable by hardware. The three
changes below are where it was not.

## The emergency stop is asked for and never observed

`wanted/track` carries `on`, `stopped` and `off`, and `stopped` is the
emergency stop. `device/track` carried the same three values, and no publisher
can produce the middle one. On a station driven directly the supply reads on
again the moment the broadcast is out
([#463](https://github.com/rails49/control/issues/463)). Over JSON the state
that would mean it is rejected on write and reported as unknown on read.

The reading that says this is a defect in the row is wrong. An emergency stop
leaves the rails live — that is what distinguishes it from cutting the supply,
and the distinction is physical rather than a modelling choice. Power removed
takes away the only channel that could stop a locomotive with a stay-alive,
which keeps rolling for a second or more with nothing able to reach it, while
sound decoders reboot and each one resumes on power return by its own rules.
An emergency stop that removes power removes the ability to stop the train.

So the supply reading `on` under an emergency stop is not a gap in reporting.
It is the truth about the supply. **`device/track` becomes `on` and `off`**,
and the asymmetry between the halves stands: what the railroad may be asked
for is not bounded by what a sensor can answer.

The row is also not JMRI's limit, which is worth recording because ADR-0043
said it was. `PowerManager` in JMRI's core has `IDLE`, documented as track
power alive with the command station broadcasting stop to all mobile
decoders, and several command stations implement it. The JSON servlet accepts
neither writing it nor reporting it, although its own schemas permit the value
in both directions and its own help page documents it. The limit is a
protocol surface, not JMRI and not the hardware.

## `state/power` holds the emergency stop

`state/power` is what the dispatcher and every UI read, and SYSTEM.md has it
folded from `device/track`, deliberately never from having commanded
anything. With `stopped` gone from the observed row, that rule leaves
[ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)'s
*emergency stop — clear it before driving* with no source: a second after the
press the board is green again and the person who pressed it has nothing
telling them the railroad is waiting for them.

**`layout` holds it.** It wrote `stopped`, so it knows, and it publishes
`state/power: stopped` from its own command until a person clears it. This is
the one value on that row not folded from hardware, and the reason is that no
hardware can hold it. `on` and `off` fold exactly as before.

## A translator reads the drawing

`device/sensor` is addressed by the block end it watches, and SYSTEM.md's rule
is that whoever publishes it is configured with the names it must publish, so
no detector geometry reaches above the layout interface. That works for a
camera, which can be told what to call itself, and cannot work for a system
whose sensors are named by that system and whose protocol requires the system
name.

The topic does not move: it is `<block>.<end>` on every railroad, so a trace
is comparable between installations and nothing above `layout` learns anything
new. **The drawing carries the name the hardware knows a sensor by**, per
block end, defaulting to the same string and editable in the UI. The drawing
already carries hardware addresses
([ADR-0022](0022-a-symbol-carries-its-hardware-address.md)), so this is the
place that already exists for it, and one place means it cannot drift.

The cost is real and is the reason this is recorded rather than assumed:
**a translator that publishes sensors reads the store, and so has a railroad
identity it has not had.** Today one takes a connection and no railroad. A
translator remains a translator — it holds no ownership table, acts on the
addresses it recognises, and ignores the rest (ADR-0043) — but it is no longer
configured by its command line alone.

The name stays out of the payload. `device/sensor` is retained, so a hardware
name carried in a message published before a drawing edit would sit on the
broker contradicting the drawing. A field that duplicates an answer the
drawing already gives can go stale; the drawing cannot.

## A refusal is reported where it can be seen

The failure behind #463 was a station answering and not obeying: every row
truthful, link up, power on, and no train moving. Nothing in the vocabulary
could carry it, and nothing can. DCC is broadcast with no return path for most
decoders, so there is no acknowledgement to wait for. That does not change.

One thing narrower than it is available: whether the hardware refused a
command or could not parse it. **`device/refused/<id>` is added**, keyed by
the publisher's own id like `device/link` and carrying `addr` where the
refusal had one, with free text for the reason. It is not a device state. It
is the publisher's report on its own last exchange, each refusal overwriting
the last, so nothing has to remember which addresses are in a refused state.

What it catches is misconfiguration — an address the hardware does not have, a
value out of range, an aspect a mast will not accept — which is common and
today entirely silent. What it misses is the failure that motivated it. It is
carryable over JSON, where errors are correlated to the command by the
request's id, and not over a shared broadcast port, where an error line cannot
be attributed to our own command rather than another client's. A row that
reports where it can and stays quiet where it cannot is worth having on those
terms, and this is the line between it and the faked observations
[ADR-0022](0022-a-symbol-carries-its-hardware-address.md) refuses: a refusal
that is published happened, and one that is not published is not evidence that
none occurred.

## Decision

1. `device/track` is `on` and `off`. `wanted/track` keeps its three values.
2. `state/power` reads `stopped` while `layout` holds an emergency stop it
   commanded, and is folded from `device/track` otherwise.
3. Each translator implements `stopped` as well as its hardware allows and
   never by removing power.
4. `wanted/function`'s `value` is a boolean.
5. The drawing carries a hardware sensor name per block end, defaulting to
   `<block>.<end>`; whoever publishes `device/sensor` reads it from the store.
6. `device/refused/<id>` is added, with `id`, an optional `addr`, and `detail`.
7. `wanted/signal` keeps three aspects, `wanted/point` keeps two positions, and
   `device/point` is published only where a position is measured.

## Alternatives not taken

**Bound the vocabulary by what one protocol can express.** The argument for it
is strong — supporting fifty command stations is work already done, and
JMRI has done it. The argument against is that a protocol surface is not the
railroad. Its schemas are unenforced and have drifted from its own
implementation in at least three places found while checking these rows, and a
field that makes multi-station addressing possible shipped without a version
bump, so a client cannot learn from the handshake whether the server has it.
Deleting a value the railroad needs because a Java servlet does not model it
would repeat, one level up, the mistake of designing around a single product.
The protocol is the best available evidence about what real hardware can do,
and evidence is what it stays.

**Map the emergency stop onto power off.** Rejected for the stay-alive
reason above, and because it would collapse ADR-0041's distinction between a
railroad someone stopped and a railroad someone has not switched on yet.

**Publish a faked `device/point` for turnouts without feedback**, so a UI can
draw positions. Not needed: `wanted/point` is retained and carries the
commanded position for every turnout, which is the only thing a fake could
have been built from. Faking it would cost the ability to tell a measured
position from an assumed one on a railroad where some turnouts have feedback
and some do not.

**Carry a range on `wanted/function`**, so more capable hardware is not
excluded in advance. There is nothing to exclude: a DCC function is one bit,
and every translator would clamp. What people mean by a range is decoder
programming, which is a different capability and would be a different row.

**Key `device/refused` by device address** rather than by publisher, so a UI
could mark the offending turnout. It would require a translator to remember
which addresses are refusing and when they stop, which is the table no
translator holds. A UI that wants that view can build it from the stream.

## Consequences

`wanted/function`'s `value` changes from the strings `off` and `on` to a
boolean, which is a payload change and lands as its own communication issue.
So does each other changed row; the rows this decision leaves alone stay where
they are, with the argument for them in
[docs/layout/DEVICES.md](../layout/DEVICES.md).

A translator that publishes sensors needs store access and a railroad, which
is a deployment change as well as a code one, and the app boundary test still
holds: it reads the store over the CRUD contract like any other app, and
imports no app but `tc49.lib` and itself.

`state/power` acquires a value `layout` clears rather than observes, so
`layout` holds one piece of state it did not hold before. ADR-0062 refused a
"cut in flight" flag on the grounds that it was a second piece of state in the
app; this is the first, and it is held because a person needs to see it,
which that flag was not.

Nothing above the layout interface changes. The dispatcher holds a run on
`stopped` exactly as it held it before (ADR-0041), and reads the same row to
do it.
