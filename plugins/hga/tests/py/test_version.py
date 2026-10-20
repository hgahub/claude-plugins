"""Release guards must reject inconsistent or invalid versions before tagging."""

import json
from pathlib import Path
import runpy
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[4]
version = runpy.run_path(str(ROOT / "scripts/version.py"))


def copy_manifests(root):
    for path in (version["PLUGIN"], version["MARKETPLACE"]):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, root / path)


def test_bump_keeps_manifests_in_sync_and_preserves_metadata(tmp_path):
    copy_manifests(tmp_path)
    paths = (version["PLUGIN"], version["MARKETPLACE"])
    before = [json.loads((tmp_path / path).read_text(encoding="utf-8")) for path in paths]
    current = version["check"](tmp_path)
    major, minor, patch = version["version_tuple"](current)
    target = f"{major}.{minor}.{patch + 1}"
    version["bump"](target, tmp_path)
    assert version["check"](tmp_path, f"v{target}") == target
    after = [json.loads((tmp_path / path).read_text(encoding="utf-8")) for path in paths]
    before[0]["version"] = target
    next(entry for entry in before[1]["plugins"] if entry["name"] == "hga")["version"] = target
    assert after == before


@pytest.mark.parametrize("invalid", ["1.2", "v1.2.3", "01.2.3", "1.2.3-rc.1", "1.2.3+build", "1.2.3\n", None])
def test_invalid_version_does_not_write(tmp_path, invalid):
    copy_manifests(tmp_path)
    paths = (version["PLUGIN"], version["MARKETPLACE"])
    before = [(tmp_path / path).read_bytes() for path in paths]
    with pytest.raises(ValueError, match="stable X.Y.Z"):
        version["bump"](invalid, tmp_path)
    assert [(tmp_path / path).read_bytes() for path in paths] == before


def test_same_or_lower_version_and_wrong_tag_are_rejected(tmp_path):
    copy_manifests(tmp_path)
    current = version["check"](tmp_path)
    for target in (current, "0.0.0"):
        with pytest.raises(ValueError, match="greater"):
            version["bump"](target, tmp_path)
    for tag in (current, "v99.99.99", f"v{current}-rc.1"):
        with pytest.raises(ValueError, match="must be"):
            version["check"](tmp_path, tag)


def test_mismatched_manifests_block_checks_and_bumps(tmp_path):
    copy_manifests(tmp_path)
    path = tmp_path / version["MARKETPLACE"]
    data = json.loads(path.read_text(encoding="utf-8"))
    next(entry for entry in data["plugins"] if entry["name"] == "hga")["version"] = "99.99.99"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="differ"):
        version["check"](tmp_path)
    with pytest.raises(ValueError, match="differ"):
        version["bump"]("100.0.0", tmp_path)
