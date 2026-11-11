"""Writing a file of the store in one step (#1223).

``write`` puts the bytes in a temporary file beside the path, named
``.<name>.<random>.tmp``, and moves it onto the path with ``os.replace``. A
reader sees the old file or the new one, never one truncated and part
written. The leading ``.`` keeps a temporary file out of what the backup
names, and the backup leaves ``.*.tmp`` out of what it commits.
"""

import os
import tempfile
from pathlib import Path


def write(path: Path, data: str | bytes) -> None:
    """Replace `path` with `data`, a `str` encoded as UTF-8. On an error the
    file at `path` is as it was and the temporary file is gone."""
    if isinstance(data, str):
        data = data.encode()
    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
