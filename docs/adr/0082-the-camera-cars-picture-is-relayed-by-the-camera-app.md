# The camera car's picture is relayed by the camera app

Part of [#851](https://github.com/rails49/control/issues/851) and [#850](https://github.com/rails49/control/issues/850).

A throttle shows the view from a camera riding in front of the train. The
camera is too big for a locomotive, so it rides on a car of its own, the
camera car, which a person couples in front of whichever train they drive. The
camera speaks plain HTTP with Basic auth and sends MJPEG. A page cannot reach
it: a UI talks only to the bus, the store and its own app's face
([rails49/.github ADR-0002](https://github.com/rails49/.github/blob/main/docs/adr/0002-a-ui-talks-to-the-bus-the-store-and-its-own-apps-face.md)),
and an HTTPS page cannot embed an HTTP stream.

## Decision

1. **A camera is a property of a car.** A car may carry a camera address,
   edited on the Stock screen like a decoder address. The car is in its
   train's list of cars, as every coupled car must be for the train's length
   to be right.
2. **A throttle shows the picture of the camera in the train it holds,** and
   the train's thumbnail when there is none or the stream fails. Which way
   the camera looks is the camera car's: run the train the other way and the
   picture looks backwards.
3. **A new app, `camera`, relays the picture.** It reads the camera's MJPEG
   and serves it on control's origin as a private face for control's UI. It
   is written for this job, modelled on
   [iot49/pnzeo](https://github.com/iot49/pnzeo) rather than importing it.

## Considered

- **Show the installation's one camera whatever train is held.** No car
  property, but a person driving one train would watch another.
- **Relay in `occupancy`, which already handles cameras.** Its cameras watch
  the layout to detect trains; this one rides a train for a person to look
  through. The subject is control's railroad, so the face is control's.
