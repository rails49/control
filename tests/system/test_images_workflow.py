"""What `.github/workflows/images.yml` promises the installation's release
workflow (rails49/.github#71 decisions 1, 2 and 8, #1216).

It is called, never triggered: no pull request or merge builds an image. It
takes a commit, builds both images at it on each architecture's own runner,
and outputs both digests. It also hands over this stack's box files: the
compose file and every file it mounts.

The workflow runs in the calling repository's context, so a checkout or a
build that leaves the repository to its default reads `installation`, not
this one. Each names it.
"""

from fnmatch import fnmatch
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]

WORKFLOW = ROOT / ".github/workflows/images.yml"
COMPOSE = ROOT / "deploy/compose.yaml"

RUNNERS = ["ubuntu-24.04", "ubuntu-24.04-arm"]


def workflow() -> dict[Any, Any]:
    return cast(dict[Any, Any], yaml.safe_load(WORKFLOW.read_text()))


def triggers() -> dict[str, Any]:
    """`on`, which YAML 1.1 reads as `True`."""
    document = workflow()
    return cast(dict[str, Any], document.get("on", document.get(True)))


def steps() -> list[dict[str, Any]]:
    jobs = cast(dict[str, dict[str, Any]], workflow()["jobs"])
    return [step for job in jobs.values() for step in job.get("steps", [])]


def uses(action: str) -> list[dict[str, Any]]:
    return [s for s in steps() if str(s.get("uses", "")).startswith(action + "@")]


def test_it_is_only_called() -> None:
    assert list(triggers()) == ["workflow_call"]


def test_it_takes_a_commit() -> None:
    commit = triggers()["workflow_call"]["inputs"]["commit"]
    assert commit["required"] is True
    assert commit["type"] == "string"


def test_it_outputs_both_digests() -> None:
    outputs = triggers()["workflow_call"]["outputs"]
    assert {"control", "control-web"} <= set(outputs)


def test_it_builds_on_both_native_runners() -> None:
    jobs = cast(dict[str, dict[str, Any]], workflow()["jobs"])
    matrices = [
        job["strategy"]["matrix"].get("runner")
        for job in jobs.values()
        if "strategy" in job
    ]
    assert RUNNERS in matrices


def test_every_checkout_names_this_repository_and_the_commit() -> None:
    checkouts = uses("actions/checkout")
    assert checkouts
    for step in checkouts:
        assert step["with"]["repository"] == "rails49/control"
        assert "commit" in step["with"]["ref"]


def test_every_build_reads_the_checkout() -> None:
    """build-push-action's default context is the calling repository."""
    builds = uses("docker/build-push-action")
    assert builds
    for step in builds:
        assert step["with"]["context"] == "."


def mounted() -> set[str]:
    """The files under `deploy/` the compose file mounts."""
    document = cast(dict[str, Any], yaml.safe_load(COMPOSE.read_text()))
    services = cast(dict[str, dict[str, Any]], document["services"])
    found: set[str] = set()
    for service in services.values():
        for volume in service.get("volumes", []):
            source = str(volume).split(":")[0]
            if source.startswith("./"):
                found.add("deploy/" + source[2:])
    return found


def test_the_box_files_are_the_compose_file_and_what_it_mounts() -> None:
    uploads = [
        s
        for s in uses("actions/upload-artifact")
        if s["with"]["name"] == "control-box-files"
    ]
    assert len(uploads) == 1
    paths = set(str(uploads[0]["with"]["path"]).split())
    assert paths == {"deploy/compose.yaml"} | mounted()
    assert "deploy/mosquitto.conf" in paths


def test_each_join_downloads_only_its_own_images_digests() -> None:
    """`control`'s pattern must not match `control-web`'s artifacts (#1221)."""
    jobs = cast(dict[str, dict[str, Any]], workflow()["jobs"])
    upload = next(
        s
        for s in jobs["build"]["steps"]
        if str(s.get("uses", "")).startswith("actions/upload-artifact@")
    )
    download = next(
        s
        for s in jobs["join"]["steps"]
        if str(s.get("uses", "")).startswith("actions/download-artifact@")
    )

    def expand(template: str, image: str, runner: str = "*") -> str:
        return template.replace("${{ matrix.image }}", image).replace(
            "${{ matrix.runner }}", runner
        )

    images = ["control", "control-web"]
    for image in images:
        pattern = expand(download["with"]["pattern"], image)
        for other in images:
            for runner in RUNNERS:
                name = expand(upload["with"]["name"], other, runner)
                assert fnmatch(name, pattern) == (other == image), (pattern, name)
