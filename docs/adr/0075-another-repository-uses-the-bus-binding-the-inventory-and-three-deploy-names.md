# Another repository uses the bus binding, the inventory and three deploy names

Resolves [#766](https://github.com/rails49/control/issues/766). Applies the
organisation's
[ADR-0006](https://github.com/rails49/.github/blob/main/docs/adr/0006-the-bus-contract-is-controls-and-travels-when-something-reads-it.md)
and dccex's
[ADR-0014](https://github.com/rails49/dccex/blob/main/docs/adr/0014-the-translator-is-on-the-bus-through-controls-package.md).

dccex takes `tc49` from control `main`, pinned by its lock (dccex ADR-0014).
It imports `tc49.lib.bus`, `mqtt`, `inventory`, `loading`, `payload` and
`startup` in `src/`, and `clock`, `layout`, `roster` and the `tc49.layout` app
in its tests. Its compose file dials `broker:1883` and `store:8765`, and routes
`/mqtt` to the Traefik service `tc49-mqtt`, which only control's labels
declare. jmri#1 plans the same dependency. control declared none of this.

The two halves fail differently on the box. A Python rename in control reaches
dccex only when its pin moves, and dccex's CI catches it then. A renamed
service, port or Traefik service breaks the translator at the next control
deploy: track power cannot be switched on and the trains do not answer, and no
test in either repository notices.

Org ADR-0006 already says `lib/bus.py` and `lib/mqtt.py` are the Python
binding and `lib/payload.py` is not. This ADR records what it left open.

## Decision

1. **Another repository may import `tc49.lib.bus`, `tc49.lib.mqtt`,
   `tc49.lib.clock` and `tc49.lib.inventory`, and nothing else of `tc49`.**
   These are the binding, the clock it stamps with, and the inventory BUS.md
   names as the machine-readable contract.
2. **Another repository may rely on three deploy names in
   `deploy/compose.yaml`:** the service `broker` on the `rails49` network, with
   native MQTT on 1883; the service `store` on the `rails49` network, with its
   face on 8765; and the Traefik service `tc49-mqtt`, the broker's WebSocket
   listener.
3. **`tests/system/test_what_another_repository_uses.py` holds both lists.** A
   pull request that changes either list changes the test and files an issue in
   each repository that uses it: dccex and jmri.
4. **`startup`, `loading`, `payload`, `layout`, `roster` and every app stay
   control's to change without notice.** A payload shape is still a BUS.md
   change, and a BUS.md change still owes its readers an issue.

## Consequences

- dccex stops importing `payload`, `loading`, `startup`, `lib.layout`,
  `lib.roster` and `tc49.layout`, and writes the small part of them it uses
  itself. `tests/dccex/test_layout_to_station.py`, which runs control's
  `layout` app inside dccex's tests, goes: each side tests its half of the
  power seam.
- `docs/ARCHITECTURE.md` and `CLAUDE.md` name the four modules and the three
  deploy names, in place of "`tc49.lib` and nothing else" and "the desired half
  of the device vocabulary".
- control's refactors of `loading`, `layout` and `payload` (#757, #762, #763)
  are not held to dccex's imports. A change to an inventory name is.
- jmri#1's import test narrows to the four modules.

## Considered

- **Declare everything dccex imports today.** Cheap now, but every later
  refactor of control's model is held to dccex's imports.
- **dccex meets control only through BUS.md and the store's face.** About 500
  lines in dccex, mostly a second MQTT client, the same again in jmri, and the
  copies kept in step with BUS.md by hand. dccex ADR-0014 rejected it.
- **A shared package of its own, pinned by tag as look is.** Every new topic
  becomes a release and a bump in control too, and the inventory changes
  often. Not worth it for two consumers.
