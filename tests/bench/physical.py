"""A railroad for a suite to run on, read off the checkout (#314).

What stood here was the harness for a run on the physical binding: a plain TCP
listener standing in for the command station's mirror, and the waiting a
socket on another thread needs. The translator that binding was half of left
for [`rails49/dccex`](https://github.com/rails49/dccex) with #587, and the
station, the address parsing and the waits went with the suite that drove
them. What is left is the one thing two suites still share.
"""

from tc49.bench.runner import railroad
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.store import AssetStore
from tests.harness import ASSETS, railroads


def a_railroad() -> tuple[Layout, Roster]:
    """Some railroad this checkout has: its layout and the stock it owns."""
    return railroad(AssetStore(ASSETS), railroads()[0])
