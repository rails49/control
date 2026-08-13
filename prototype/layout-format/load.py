"""PROTOTYPE — throwaway. Ticket #5, map #1.

Loads a layout + scenario in the proposed format and prints everything the
dispatcher would derive from them, so the format can be judged on whether it
carries enough (and no more).

    uv run --with pyyaml python prototype/layout-format/load.py \
        prototype/layout-format/meet.scenario.yaml
"""

import sys
from itertools import combinations
from pathlib import Path

import yaml

OTHER = {"A": "B", "B": "A"}


def parse_end(text):
    block, _, end = text.partition(".")
    return block, end


class Layout:
    def __init__(self, doc):
        self.name = doc["layout"]
        self.blocks = doc["blocks"]
        self.transits = {}  # (connection, transit) -> {end, end}
        self.conflicts = set()  # frozenset of two transit keys
        self.at_end = {}  # end -> [transit key]

        for cname, conn in doc["connections"].items():
            names = list(conn["transits"])
            concurrent = {
                frozenset((cname, n) for n in pair)
                for pair in conn.get("concurrent", [])
            }
            for tname in names:
                key = (cname, tname)
                ends = {parse_end(e) for e in conn["transits"][tname]}
                self.transits[key] = ends
                for end in ends:
                    self.at_end.setdefault(end, []).append(key)
            # inversion: everything conflicts unless declared concurrent
            for a, b in combinations(names, 2):
                pair = frozenset(((cname, a), (cname, b)))
                if pair not in concurrent:
                    self.conflicts.add(pair)

    def terminal_blocks(self):
        connected = {block for block, _ in self.at_end}
        return sorted(b for b in self.blocks if b not in connected) + sorted(
            b
            for b in self.blocks
            if b in connected and sum((b, e) in self.at_end for e in "AB") == 1
        )

    def step(self, block, exit_end):
        """Every (transit, next block, next entry end) leaving block via exit_end."""
        for key in self.at_end.get((block, exit_end), []):
            for nblock, nend in self.transits[key]:
                if (nblock, nend) != (block, exit_end):
                    yield key, nblock, nend

    def route(self, block, depart_end, dest, length):
        """Shortest route by transit count; lexicographic tie-break (per #3)."""
        if block == dest:
            return []
        best, frontier = None, [((block, OTHER[depart_end]), [], {block})]
        while frontier:
            nxt = []
            for (blk, entry), path, seen in frontier:
                for key, nblock, nend in self.step(blk, OTHER[entry]):
                    if nblock in seen or self.blocks[nblock]["length"] < length:
                        continue
                    ext = path + [key, nblock]
                    if nblock == dest:
                        ids = [s for s in ext if isinstance(s, str)]
                        if best is None or ids < best[0]:
                            best = (ids, ext)
                    else:
                        nxt.append(((nblock, nend), ext, seen | {nblock}))
            if best:
                return best[1]
            frontier = nxt
        return None


def main(scenario_path):
    path = Path(scenario_path)
    scen = yaml.safe_load(path.read_text())
    layout = Layout(yaml.safe_load((path.parent / scen["layout"]).read_text()))

    print(f"layout {layout.name}: {len(layout.blocks)} blocks, "
          f"{len(layout.transits)} transits")
    print(f"  terminal blocks: {', '.join(layout.terminal_blocks())}\n")

    print("conflict matrix (expanded from `concurrent` inversion)")
    for cname in dict.fromkeys(c for c, _ in layout.transits):
        keys = [k for k in layout.transits if k[0] == cname]
        conc = [
            f"{a[1]}+{b[1]}"
            for a, b in combinations(keys, 2)
            if frozenset((a, b)) not in layout.conflicts
        ]
        print(f"  {cname:<13} {len(keys)} transits, "
              f"concurrent: {', '.join(conc) if conc else '(none — fully exclusive)'}")

    print("\nrequests")
    for req in scen["requests"]:
        train = scen["trains"][req["train"]]
        blk, end = parse_end(req["from"])
        # Real loader: check `from` against the train's starting block for its
        # first request, and against its actual block at admission thereafter.
        route = layout.route(blk, end, req["to"], train["length"])
        if route is None:
            print(f"  t={req['at']:>3} {req['train']} {req['from']} -> "
                  f"{req['to']}: UNROUTABLE (rejected)")
            continue
        steps = " ".join(
            s[1] if isinstance(s, tuple) else f"[{s}]" for s in route
        )
        print(f"  t={req['at']:>3} {req['train']} ({train['length']}mm) "
              f"{req['from']} -> {req['to']}")
        print(f"         route: [{blk}] {steps}   "
              f"({len(route) // 2} transits = {len(route) // 2} ticks)")


if __name__ == "__main__":
    main(sys.argv[1])
