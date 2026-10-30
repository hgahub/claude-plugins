"""Release guards must reject inconsistent or invalid versions before tagging."""

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import textwrap

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


def test_installs_follow_stable():
    # An update installs what the marketplace's ref holds, so every documented install pins #stable.
    for doc in ("README.md", "plugins/hga/README.md", "docs/quickstart.md"):
        adds = [line for line in (ROOT / doc).read_text(encoding="utf-8").splitlines()
                if line.startswith("claude plugin marketplace add ")]
        assert adds == ["claude plugin marketplace add hgahub/claude-plugins#stable"], doc


def stable_step() -> str:
    """The run script of release.yml's `Move stable to the release` step."""
    lines = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "- name: Move stable to the release")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run]) - len(lines[run].lstrip())
    body = []
    for line in lines[run + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return textwrap.dedent("\n".join(body))


def find_bash():
    if os.name != "nt":
        return shutil.which("bash")
    # On Windows, PATH's bash.exe can be the WSL launcher: take Git for Windows' own <Git>/bin/bash.exe, found above
    # git.exe (<Git>/cmd, <Git>/bin or <Git>/mingw64/bin).
    git = shutil.which("git")
    bashes = [p / "bin" / "bash.exe" for p in Path(git).resolve().parents] if git else []
    return next((str(b) for b in bashes if b.exists()), None)


BASH = find_bash()


@pytest.mark.skipif(BASH is None or shutil.which("git") is None, reason="needs bash and git")
def test_release_creates_stable_then_only_fast_forwards_it(tmp_path):
    (tmp_path / "step.sh").write_text(stable_step(), encoding="utf-8")
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path / "w"), *a], check=True, capture_output=True,
                                    text=True).stdout.strip()
    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "origin.git")], check=True)
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(tmp_path / "w")], check=True,
                   capture_output=True)
    for c in "ABC":
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", c)
    a, b, c = (git("rev-parse", f"HEAD~{n}") for n in (2, 1, 0))

    def run(sha):  # gh is a shell function that only prints the call
        git("fetch", "-q", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*")
        env = {**os.environ, "GITHUB_SHA": sha, "RELEASE_TAG": "vX", "GITHUB_REPOSITORY": "o/r"}
        res = subprocess.run([BASH, "-e", "-c", 'gh() { echo "gh $*"; }; . ../step.sh'], cwd=tmp_path / "w",
                             env=env, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        return res.stdout.strip()

    assert run(b) == f"gh api repos/o/r/git/refs -f ref=refs/heads/stable -f sha={b}"
    git("push", "-q", "origin", f"{b}:refs/heads/stable")
    assert run(a).startswith("stable already contains")  # an older tag
    assert run(b).startswith("stable already contains")  # a rerun
    assert run(c) == f"gh api -X PATCH repos/o/r/git/refs/heads/stable -f sha={c} -F force=false"
