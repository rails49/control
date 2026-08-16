# Turnout position is inferred by the panel

The [panel](../ui/PANEL.md) shows turnout positions, although the app has no turnouts. It
subscribes to the existing `tc49/drive/align` command, which names a connection
and a transit, and works out from its own drawing which turnouts that transit
traverses and how each must lie.

This keeps [SYSTEM.md](../SYSTEM.md#layout-interface) intact where it says
commands are "transit-level, never turnout-level" and that the
transit-to-turnout-positions table is private hardware configuration. The panel
is not the app: it may hold that table because its drawing already contains the
turnout geometry the table is made of. Nothing changes in the layout format, the
bus inventory, or [LAYOUT.md](../store/LAYOUT.md)'s position that turnouts are
"inexpressible until a later effort gives turnouts identity".

The alternative was to give turnouts identity, publish
`tc49/layout/turnout_aligned` from real point feedback, and have the panel show
reported position. That is the more truthful design and was rejected only on
timing. It costs a layout format change, a bus inventory entry, and revising
settled ADRs, and it buys nothing until hardware with point-position sensors
exists. Under the simulator, reported position would be a restatement of the
command.

What is given up is real: the panel shows commanded position, so a point that
failed to throw looks correct. That is invisible under the simulator and matters
the day physical hardware appears, which is exactly when reported position
becomes worth adding. It arrives additively, with the panel preferring reported
over inferred and treating a divergence between the two as a visible fault. The
drawing has already done the hard part by recording which turnouts exist.
