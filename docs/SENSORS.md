# Sensors

How a layout owner whose track sensors are wired to hardware of their own gets
the readings to `control`. A script of the owner's reads the hardware and
publishes each reading on the bus. The contract it meets is
[`tc49/layout/sensor` in BUS.md](BUS.md#event-inventory), which says what a
report carries and what a publisher owes. This page does not repeat it. No
script is kept in any repository.

## The broker

Native MQTT at the box's LAN address, port 1883, with no authentication
([DEPLOY.md](DEPLOY.md), [deploy/mosquitto.conf](../deploy/mosquitto.conf)).

## A report

One report, from a shell:

```sh
mosquitto_pub -h box -p 1883 -t tc49/layout/sensor \
  -m '{"addr": "yard_w.B", "occupancy": "occupied"}'
```

`occupancy` is `occupied`, `clear` or `unknown`. A script sends reports like
this one as often as BUS.md asks, changed or not.

## Naming

`addr` is `<block>.<end>`: the block's name on the drawing, and `A` or `B` for
the end. Mapping the hardware's own ids to block ends is the script's job, for
example a table in the script. It needs neither the drawing's `sensors` field
([Hardware ids](store/DRAWING.md#hardware-ids),
[ADR-0063](adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md))
nor `tc49/layout/state/railroad`.

Loading another railroad can change which block ends exist
([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)),
so the table has to match the railroad loaded. A report for a block end not on
the drawing still gets a settled row, but is never listed on
`tc49/layout/state/unknown_sensors`. A misspelled `addr` is seen from the other
side: the block end it was meant for stays listed, with the reason
`no report since start`.

## One publisher per block end

Each block end gets its reports from one source
([BUS.md](BUS.md#event-inventory)). A railroad may mix sources across block
ends, for example a camera in the open and track sensors in a tunnel.

The camera is [rails49/occupancy-service](https://github.com/rails49/occupancy-service),
with its [`control` profile](https://github.com/rails49/occupancy-service#the-shipped-profiles).
It reports each sensor its archive places, under the id the archive gives it.
The block ends a script reports get no sensor in the archive.

## Which sensors fit

BUS.md asks that a sensor read `occupied` without a break from the moment a
train's head reaches it until its tail has left it.

- Current detection fits when every car has resistor wheelsets. A car without
  them is not seen, and the gap it leaves reads `clear`.
- Reed switches and IR beam-breaks fire briefly as a magnet or a car passes,
  or drop out between cars. The script has to hold the level itself, and this
  page gives no recipe for that.

`layout`'s settling time filters a flicker shorter than it, and nothing
longer: a `clear` that lasts is taken for the train's tail
([layout/README.md](layout/README.md#sensors),
[#1167](https://github.com/rails49/control/issues/1167)).

## `unknown`

Send `unknown` when the script cannot say what a sensor reads: the hardware
does not answer, or the script has not read it yet. Once `unknown` has stood
for the settling time, the sensor is listed on `state/unknown_sensors` and the
dispatcher grants nothing into, out of or through its block.

`reason` goes with `unknown` only. It is free text for a person: the page shows
it and nothing acts on what it says. Say what is wrong, such as
`no answer from the sensor board`.

A script that stops sending has its sensors listed once the sensor silence
runs out, with the reason `no report for <n> s`. The silence is set in the
Settings dialog ([EDITOR.md](ui/EDITOR.md)). Sending `unknown` for every
sensor before a clean stop says why at once.

## The other direction

A program other than `control` that reads the camera's readings is described
in occupancy-service's
[Other programs](https://github.com/rails49/occupancy-service#other-programs).
