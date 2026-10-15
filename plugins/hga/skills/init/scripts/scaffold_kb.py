"""Creates a new hga knowledge base from the plugin's template.

Usage: python scaffold_kb.py <target-dir> [--add-missing]

Copies templates/knowledge/ into <target-dir> and fills in today's date. A missing or empty target is
created; a non-empty one is refused (exit 3) unless --add-missing is given, which only adds the files that
do not exist yet and never overwrites. Prints every file it wrote. Does not run git and does not write
hga.config.json — /hga:init does both.

Exit code: 0 done, 3 target not empty, 2 wrong usage.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "knowledge"


def scaffold(target: Path, add_missing: bool = False, today: str | None = None) -> list[str]:
    today = today or date.today().isoformat()
    written = []
    for src in sorted(TEMPLATE.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(TEMPLATE)
        dst = target / rel
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8").replace("{{DATE}}", today)
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:  # write_text(newline=) needs Python 3.10
            fh.write(text)
        written.append(rel.as_posix())
    return written


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--add-missing", action="store_true", help="add missing files to a non-empty folder")
    a = ap.parse_args(argv)
    target = Path(a.target).expanduser()
    if target.exists() and not target.is_dir():
        print(f"not a directory: {target}", file=sys.stderr)
        return 2
    if target.is_dir() and any(p.name != ".git" for p in target.iterdir()) and not a.add_missing:
        print(f"not empty: {target} — choose another folder, or add only the missing files with --add-missing",
              file=sys.stderr)
        return 3
    target.mkdir(parents=True, exist_ok=True)
    written = scaffold(target, a.add_missing)
    for rel in written:
        print(f"wrote {rel}")
    print(f"{len(written)} file(s) written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
