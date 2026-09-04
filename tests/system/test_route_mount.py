"""The proxy mounts a route directory, not a route file (#353).

A single-file bind mount binds the inode. `git pull` replaces a file rather
than writing through it, so the container went on serving the table it was
created with and `--providers.file.watch=true` watched something nothing
touched any more; only recreating the container by hand loaded a new table.
Mounting the directory is what makes a route change land on the next deploy,
and it is one character away from the mount that does not, so it is checked
rather than remembered.

The directory a site mounts holds that site's file and no other. Traefik asks
for a certificate at startup for every router it can see, so a box seeing both
sites would fetch a certificate for a name that is not its own — which is why
selecting the site in the mount cannot become selecting it in a directory
holding both.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

ROUTES = ROOT / "deploy/routes"
SITES = sorted(p.name for p in ROUTES.iterdir() if p.is_dir())


def proxy() -> dict[str, Any]:
    compose: dict[str, Any] = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
    service: dict[str, Any] = compose["services"]["proxy"]
    return service


MOUNT = re.compile(r"^(.+?):(/.+?)(?::[a-z,]+)?$")
"""A short-form volume, `source:target[:mode]`. The source holds a colon of
its own — `${TC49_SITE:-dev}` — so the split is on the colon that begins an
absolute path rather than on the first one."""


def route_mount() -> tuple[str, str]:
    """The proxy's route mount, as `(source, target)`."""
    volumes: list[str] = proxy()["volumes"]
    mounts = [MOUNT.match(v) for v in volumes if v.startswith("./routes")]
    assert len(mounts) == 1, f"the proxy mounts the routes once; {volumes}"
    mount = mounts[0]
    assert mount is not None, f"the route mount is `source:target[:mode]`; {volumes}"
    return mount[1], mount[2]


def test_the_route_mount_is_a_directory_named_by_the_site() -> None:
    source, _ = route_mount()
    assert source == "./routes/${TC49_SITE:-dev}", (
        "the source is the site's directory; a path ending in the file inside "
        f"it binds an inode a pull replaces, and {source} does not"
    )


def test_the_route_mount_is_where_the_proxy_reads_its_routes() -> None:
    _, target = route_mount()
    command: list[str] = proxy()["command"]
    assert f"--providers.file.directory={target}" in command
    assert "--providers.file.watch=true" in command


@pytest.mark.parametrize("site", SITES)
def test_a_site_directory_holds_that_site_alone(site: str) -> None:
    held = sorted(p.name for p in (ROUTES / site).iterdir())
    assert held == ["site.yaml"], (
        f"the proxy sees every file in {site}, and asks for a certificate for "
        f"every router in it; {held}"
    )


def test_the_default_site_is_there() -> None:
    """`TC49_SITE` unset means `dev`, so a mount of it has to resolve."""
    assert "dev" in SITES
