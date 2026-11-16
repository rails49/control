# Publishing your own sensors

For a layout owner whose block occupancy is read by their own hardware: how a
script of theirs gets those readings to `control`. The payload and what is
asked of any publisher are BUS.md's, under
[`tc49/layout/sensor`](BUS.md#layout), and are not repeated here. No such
script is kept in any repository.

## The broker

Native MQTT at the box's LAN address, port 1883, no authentication
([DEPLOY.md](DEPLOY.md), [`deploy/mosquitto.conf`](../deploy/mosquitto.conf)).

One report, sent with `mosquitto_pub`:

```
mosquitto_pub -h <the box's LAN address> -p 1883 \
  -t tc49/layout/sensor -m '{"addr": "yard.A", "occupancy": "occupied"}'
```

A script sends one such message per sensor, as often as BUS.md asks.

## Which sensor

`addr` is the sensor, `<block>.<end>`: a block's name on the drawing and its
end, `A` or `B`. Mapping the hardware's own ids to sensors is the script's
job. It needs neither the drawing's hardware-name field
([ADR-0063](adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md),
[DRAWING.md](store/DRAWING.md#hardware-ids)) nor
`tc49/layout/state/railroad`.

Loading another railroad can change which sensors exist. A report for a sensor
not on the drawing still gets a settled row but is never listed on
`tc49/layout/state/unknown_sensors`, so a script reporting on the wrong
railroad's names is not told.

## One publisher per sensor

Each sensor has one publisher ([BUS.md](BUS.md#layout)). A railroad may mix
detectors across sensors, for example a camera in the open and current
detection in a tunnel.

## Which detectors fit

A sensor reads `occupied` from a train's head reaching the point it watches
until its tail has left it ([BUS.md](BUS.md#layout)).

- **Current detection** fits when every car has resistor wheelsets. Without
  them only what draws current is seen, and the sensor reads `clear` while the
  rest of the train is still at the point.
- **Reed switches and IR beam-breaks** fire briefly, or drop out between cars.
  The script has to hold the level itself from the train's head to its tail.
  This page gives no recipe for that.

## `unknown`

Send `unknown` for a sensor whenever the script cannot say what is at the point:
the hardware is unreachable, not calibrated, or reporting something the script
does not understand. Once that has stood for the settling time the sensor is
listed on `tc49/layout/state/unknown_sensors` and its block is out of use, until
an `occupied` or `clear` has stood for the settling time. A script that stops
sending has the same effect, but only after `sensor_silence`.

`reason` goes only with `unknown` and is free text for a person: the page shows
it, and nothing in `control` acts on what it says.

```
mosquitto_pub -h <the box's LAN address> -p 1883 -t tc49/layout/sensor \
  -m '{"addr": "yard.A", "occupancy": "unknown", "reason": "bus to the tunnel board down"}'
```
