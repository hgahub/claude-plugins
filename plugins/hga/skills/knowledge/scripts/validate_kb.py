"""Validates an hga knowledge base: frontmatter, links and wikilinks, and credential-like content.

Usage: python validate_kb.py [<knowledge-dir>] [--today YYYY-MM-DD]

Checks every Markdown page (except under .git and .maintenance):
  - frontmatter: `title`, `verified_at` (YYYY-MM-DD), `status` (verified | partially_verified |
    needs_verification | stale), optional integer `review_after_days`. Folder READMEs and the generated
    map/ pages are exempt;
  - relative Markdown links and [[wikilinks]] outside code resolve to an existing file;
  - nothing looks like a secret (tokens, private keys, passwords, bearer headers), code blocks included.
Pages past their `review_after_days` are reported as warnings.

Exit code: 0 no errors (warnings allowed), 1 errors found, 2 wrong usage.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kb_common import MD_LINK_RE, REQUIRED, STATUSES, WIKILINK_RE, code_free_lines, pages, split_frontmatter  # noqa: E402

SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("API secret key", re.compile(r"\bsk-(?:ant-|proj-|live_|test_)?[A-Za-z0-9_-]{24,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("password", re.compile(r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"]?(?!<|\$\{|\$|\*{3}|x{3}|\.\.\.|…|changeme|example|placeholder|redacted)[^\s'\"`<>]{6,}")),
)
EXEMPT_FRONTMATTER_DIRS = {"map"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_external(target: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I)) or target.startswith("#")


def check(root: Path, today: date) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    all_pages = pages(root)
    stems = {p.stem for p in all_pages}
    for p in all_pages:
        rel = p.relative_to(root).as_posix()
        text = p.read_text(encoding="utf-8")
        fields, body, first = split_frontmatter(text)
        exempt = p.name.lower() == "readme.md" or p.relative_to(root).parts[0] in EXEMPT_FRONTMATTER_DIRS
        if not exempt:
            if fields is None:
                errors.append(f"{rel}:1: missing frontmatter (--- title / verified_at / status ---)")
            else:
                for key in REQUIRED:
                    if not fields.get(key):
                        errors.append(f"{rel}:1: frontmatter field `{key}` is missing")
                st = fields.get("status")
                if st and st not in STATUSES:
                    errors.append(f"{rel}:1: status `{st}` is not one of {', '.join(STATUSES)}")
                va = fields.get("verified_at")
                verified = None
                if va:
                    if not DATE_RE.match(va):
                        errors.append(f"{rel}:1: verified_at `{va}` is not YYYY-MM-DD")
                    else:
                        try:
                            verified = datetime.strptime(va, "%Y-%m-%d").date()
                        except ValueError:
                            errors.append(f"{rel}:1: verified_at `{va}` is not a valid date")
                rad = fields.get("review_after_days")
                if rad:
                    if not rad.isdigit():
                        errors.append(f"{rel}:1: review_after_days `{rad}` is not a whole number")
                    elif verified and st != "stale" and verified + timedelta(days=int(rad)) < today:
                        warnings.append(f"{rel}: due for review (verified {va}, review after {rad} days)")
        for n, ln in code_free_lines(body, first):
            for m in MD_LINK_RE.finditer(ln):
                target = m.group(1)
                if is_external(target):
                    continue
                path = unquote(target.split("#", 1)[0])
                if path and not (p.parent / path).exists():
                    errors.append(f"{rel}:{n}: broken link: {target}")
            for m in WIKILINK_RE.finditer(ln):
                name = m.group(1).strip()
                if name not in stems and not (root / name).exists() and not (root / f"{name}.md").exists():
                    errors.append(f"{rel}:{n}: broken wikilink: [[{name}]]")
        for k, ln in enumerate(text.splitlines(), 1):
            for label, rx in SECRET_PATTERNS:
                if rx.search(ln):
                    errors.append(f"{rel}:{k}: looks like a secret ({label}) — remove it, keep only the key's name")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=os.environ.get("HGA_KNOWLEDGE_DIR", "~/.hga/knowledge"))
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for tests")
    a = ap.parse_args(argv)
    root = Path(a.root).expanduser()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    today = datetime.strptime(a.today, "%Y-%m-%d").date() if a.today else date.today()
    errors, warnings = check(root, today)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(pages(root))} page(s) · {len(errors)} error(s) · {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
