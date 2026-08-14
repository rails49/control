# Transit conflicts are declared by inversion

A connection lists which pairs of its transits are `concurrent`; every pair not
listed conflicts. The natural-reading alternative — list the pairs that
*conflict* — was rejected on the direction of its failure mode.

Layouts are hand-authored by someone drawing a railroad, so a forgotten line is
the expected error, not the exceptional one. Under inversion a forgotten line
means two transits that could have run together are serialised: the layout
costs throughput and stays safe. Under the direct form a forgotten line means
two conflicting transits are believed compatible, and the dispatcher grants
both — a collision the safety check cannot catch, because conflicts are
enforced as instantaneous admissibility at the grant rather than by `safe()`
(see [SAFETY.md](../SAFETY.md)).

It also matches the shape of real track. Ladders and plain turnouts are fully
exclusive and now declare nothing; only genuine crossings say anything at all.
The Gotthard encoding declares no `concurrent` pairs whatsoever
([layouts/gotthard.layout.yaml](../../layouts/gotthard.layout.yaml)), which is
certainly too strict for a station that size — and is exactly the kind of thing
that should cost measured throughput until the real turnout geometry is
entered, rather than being assumed permissive.
