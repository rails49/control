#!/usr/bin/env bash
# PROTOTYPE (#628): the stub camera's two pictures, made from pnzeo's sample
# snapshot. Not committed: the snapshot shows a room of a private home.
set -euo pipefail
cd "$(dirname "$0")"
cp ../../../../../pnzeo/snapshot_*.jpg take-1.jpg
uv run --no-project --with pillow python -c "
from PIL import Image
Image.open('take-1.jpg').rotate(180).convert('L').save('take-2.jpg', quality=85)"
