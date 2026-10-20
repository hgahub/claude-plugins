#!/usr/bin/env python3
"""Check hga's release version, or bump both manifests before opening a PR."""

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path("plugins/hga/.claude-plugin/plugin.json")
MARKETPLACE = Path(".claude-plugin/marketplace.json")


def version_tuple(version):
    if not isinstance(version, str) or not re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version
    ):
        raise ValueError(f"Expected a stable X.Y.Z version, got {version!r}")
    return tuple(map(int, version.split(".")))


def manifests(root):
    plugin = json.loads((root / PLUGIN).read_text(encoding="utf-8"))
    marketplace = json.loads((root / MARKETPLACE).read_text(encoding="utf-8"))
    entries = [entry for entry in marketplace["plugins"] if entry["name"] == "hga"]
    if plugin["name"] != "hga" or len(entries) != 1:
        raise ValueError("Expected one hga plugin and one hga marketplace entry")
    version_tuple(plugin["version"])
    if plugin["version"] != entries[0]["version"]:
        raise ValueError("Plugin and marketplace versions differ; reconcile them before releasing")
    return plugin, marketplace, entries[0]


def check(root=ROOT, tag=None):
    plugin, _, _ = manifests(root)
    version = plugin["version"]
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} must be v{version}")
    return version


def bump(version, root=ROOT):
    next_version = version_tuple(version)
    plugin, marketplace, entry = manifests(root)
    if next_version <= version_tuple(plugin["version"]):
        raise ValueError("The new version must be greater than the current version")
    plugin["version"] = entry["version"] = version
    for path, data in ((PLUGIN, plugin), (MARKETPLACE, marketplace)):
        (root / path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--set", metavar="X.Y.Z", help="bump both manifests; does not commit, tag or push")
    mode.add_argument("--tag", help="also require the exact release tag vX.Y.Z")
    args = parser.parse_args()
    try:
        if args.set is not None:
            bump(args.set)
        print(f"hga version: {check(tag=args.tag)}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Version check failed: {error}\n")


if __name__ == "__main__":
    main()
