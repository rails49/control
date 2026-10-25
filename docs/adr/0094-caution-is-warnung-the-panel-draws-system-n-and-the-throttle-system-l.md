# `caution` is Warnung, the panel draws system N and the throttle system L

Part of [#1026](https://github.com/rails49/control/issues/1026). Qualifies
[ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md).

ADR-0025 matched `caution` to SBB Fb 2, and the panel and the throttle light
it green with amber. On an SBB system L main signal that is Fb 2, 40 km/h.
What `caution` means here is "proceed, the next signal shows stop", which SBB
calls **Warnung** (FDV R 300.2 §5.2.2, edition A2024). A person who knows the
Swiss signals reads the wrong thing.

Without speeds, the three aspects carry what SBB signals carry:

| Aspect | Meaning | System N | System L: main signal, distant signal on its mast |
| --- | --- | --- | --- |
| `stop` | stand | Halt: red | Halt: red; distant dark |
| `caution` | proceed, next signal at stop | Warnung: amber | Fb 1: green; Warnung: two amber |
| `clear` | proceed, next signal not at stop | Fahrt: green | Fb 1: green; Ankündigung Freie Fahrt: two green |

System N (R 300.2 figs 510, 521, 526, 532) shows each with one lamp of three.
System L needs a distant signal (Vorsignal) on the main signal's mast, which
refers to the next signal (§5.1.6): four lamps, two amber across the top and
two green on a diagonal (figs 519, 528). While the main signal shows Halt the
distant signal shows Warnung or is dark; SBB usually leaves it dark at exit
signals. Both systems are in use on SBB. N dates from 1986, and the railroad
is modelled on a period before it.

## Decision

1. **`caution` is Warnung.** The bus keeps the three values and their names.
2. **The panel draws system N.** Its three-lamp row along the block keeps its
   geometry and lights one lamp: red for `stop`, amber for `caution`, green
   for `clear`.
3. **The throttle draws system L**, as the signals on the layout are. A main
   signal with two lamps, green above red, and the four-lamp distant signal
   under it as in fig 528: amber top left and top right, green middle right
   and bottom left. `stop` lights red with the distant signal dark,
   `caution` green with the two ambers, `clear` green with the two greens.
4. **A head on the layout lights what its decoder is set to.** `wanted/signal`
   carries the aspect, and which lamps it lights is wiring, not contract. The
   layout's heads are system L and light what the throttle draws.

## Consequences

- One aspect has two pictures, amber alone on the panel and green with two
  amber on the throttle, both meaning Warnung.
- A signal has more than three lamps, so **Lamp** in GLOSSARY.md stops
  saying three.
- Speed signalling, which GOALS.md leaves open, would add to either system:
  a digit on N, further lamps on L.

## Considered

- **System N everywhere.** One lamp per aspect, but the layout's period is
  before N, and the throttle shows what the driver sees on the layout.
- **System L everywhere.** Faithful, but a main and a distant signal at
  every block end does not fit the panel.
- **Keep green with amber.** It is Fb 2 on an L main signal.
