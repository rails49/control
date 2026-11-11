"""The two published images, run (rails49/.github#71, #1216).

One `control` image serves every box, so the store names whatever uid it is
started as: OpenSSH and `ssh-keygen` refuse a uid with no passwd entry, and
the backup makes its key and pushes with them. The entry comes from
`nss_wrapper` at start, and `/etc/passwd` stays root's.

`control-web` is nginx with the built UI in it, and sends `index.html` with
`Cache-Control: no-cache` (#1123).

These need a Docker daemon and a built image, so the gate skips them.
`TC49_APP_IMAGE` and `TC49_WEB_IMAGE` name the images to run, and an empty
one is unset. The images workflow sets them on each architecture's runner
before it pushes.
"""

import os
import subprocess
import time
import urllib.request

import pytest

APP = os.environ.get("TC49_APP_IMAGE") or None
WEB = os.environ.get("TC49_WEB_IMAGE") or None

UIDS = ["1000:1000", "501:20"]
"""An Ubuntu box's first account, and a mac's."""


def run(image: str, user: str, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", "--user", user, "-e", "HOME=/tmp", image, *command],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(APP is None, reason="TC49_APP_IMAGE names no image")
@pytest.mark.parametrize("user", UIDS)
def test_the_store_makes_a_key_and_reaches_ssh_as_any_uid(user: str) -> None:
    """`ssh -G` stops on a nameless uid before it reads any config, and
    `ssh-keygen` names the key after the user."""
    assert APP is not None
    made = run(
        APP,
        user,
        "store-start",
        "sh",
        "-c",
        "ssh-keygen -q -t ed25519 -N '' -f /tmp/key && ssh -G github.com >/dev/null"
        " && id -un",
    )
    assert made.returncode == 0, made.stderr
    assert made.stdout.strip() == "tc49"


@pytest.mark.skipif(APP is None, reason="TC49_APP_IMAGE names no image")
def test_the_tables_stay_roots() -> None:
    """Nothing in the container can add a line to them (#570)."""
    assert APP is not None
    listed = run(APP, "501:20", "sh", "-c", "stat -c %U:%a /etc/passwd /etc/group")
    assert listed.stdout.split() == ["root:644", "root:644"], listed.stderr
    named = run(APP, "501:20", "getent", "passwd", "501")
    assert named.returncode != 0


@pytest.mark.skipif(WEB is None, reason="TC49_WEB_IMAGE names no image")
def test_the_web_image_serves_the_ui_uncached() -> None:
    assert WEB is not None
    started = subprocess.run(
        ["docker", "run", "-d", "--rm", "-p", "127.0.0.1::80", WEB],
        capture_output=True,
        text=True,
        check=True,
    )
    container = started.stdout.strip()
    try:
        port = (
            subprocess.run(
                ["docker", "port", container, "80/tcp"],
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.split(":")[-1]
            .strip()
        )
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as answer:
                    body = answer.read().decode()
                    cache = answer.headers.get("Cache-Control")
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("nginx did not answer")
        assert '<script type="module"' in body
        assert cache == "no-cache"
    finally:
        subprocess.run(["docker", "stop", container], capture_output=True, check=False)
