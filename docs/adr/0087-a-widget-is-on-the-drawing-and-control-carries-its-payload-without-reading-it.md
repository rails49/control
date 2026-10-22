# A widget is on the drawing, and control carries its payload without reading it

Built by [#924](https://github.com/rails49/control/issues/924)–[#929](https://github.com/rails49/control/issues/929)
and [rails49/dccex#342](https://github.com/rails49/dccex/issues/342).

A person wants to see text from outside control, such as track current from a
DCC-EX script, and to send something to hardware control knows nothing about,
such as the lights. Both are placed on the drawing beside the track and shown
in the run view. Control shows the text and sends the payload, and never acts
on either.

## Decision

1. **A widget is a text, a button or a toggle.** It sits in the drawing's own
   `widgets` list, not among the symbols. It has no pins and no transits, and
   the layout is not derived from it. It is edited while the drawing can be
   edited and pressed in the run view.
2. **A widget's topic ends in its name.** The name is typed and unique within
   the drawing, and properties shows the whole topic, so whoever writes the
   listener or the script can read it off the screen:

   | Topic | Kind | Writer |
   | --- | --- | --- |
   | `tc49/ui/state/text/<name>` | state | any |
   | `tc49/ui/state/toggle/<name>` | state | any (browser) |
   | `tc49/ui/button/<name>` | event | any (browser) |

   A rename changes the topic. The railroad is not in it: a toggle named
   `lights` on any railroad is the same lights on the same box.
3. **Text and toggle rows take any writer.** Rule 1 of
   [BUS.md](../BUS.md#the-bus) forbids several writers on a state topic,
   because each may supply only part of the value
   ([ADR-0035](0035-a-topic-has-one-writing-role.md)). A widget row is
   always the whole value and the last one written is the right one, so
   that reason does not apply. A page opened later shows the current text
   and toggle position, and a listener that restarts finds the lights should
   be on. A button press is an event and is not kept.
4. **A widget payload is raw.** A button sends the payload typed for it; a
   toggle sends its on or its off payload; a text row is shown as it
   arrives. None is JSON that control defines, and none carries `at`. A page
   reads a toggle's position by comparing the row with its two payloads, so
   the two must differ. The text widget renders bold and three colours from
   ANSI codes and removes any other code.

## Consequences

- `ui` becomes a component on the bus, and BUS.md lists the three topics as
  patterns.
- Two writers of one text row overwrite each other. That is the writers'
  business.
- A deleted widget's row stays on the broker.
- rails49/dccex ADR-0013 d.4 says a script publishes nothing on the bus. A
  script posting a text row needs it amended (rails49/dccex#342).

## Considered

- **One shared topic with the widget's name in the payload.** A listener
  would have to parse the payload to find the widget it wants.
- **An address in the device vocabulary, like a point.** It suits lights on
  an accessory decoder and nothing that wants its own payload.
- **Button and toggle as events only.** A page opened later and a listener
  that restarts would not know the toggle's position.
- **A format template on the widget.** Control would then read the payload.
