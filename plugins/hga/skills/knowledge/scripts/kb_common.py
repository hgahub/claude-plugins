"""Shared helpers for the knowledge base scripts: walking the pages, frontmatter, code-free text, links."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SKIP_DIRS = {".git", ".maintenance", "node_modules", ".obsidian", ".trash"}
STATUSES = ("verified", "partially_verified", "needs_verification", "stale")
REQUIRED = ("title", "verified_at", "status")

FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
MD_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]")
ISSUE_RE = re.compile(r"(?<![\w/&])#(\d{1,6})\b")


def default_root() -> str:
    """The knowledge base folder, resolved like `hga_issue.py config`: $HGA_KNOWLEDGE_DIR, then the machine
    configuration's `knowledge_dir` ($HGA_USER_CONFIG or ~/.claude/hga/config.json), then ~/.hga/knowledge."""
    if os.environ.get("HGA_KNOWLEDGE_DIR"):
        return os.environ["HGA_KNOWLEDGE_DIR"]
    user = Path(os.environ.get("HGA_USER_CONFIG") or Path.home() / ".claude" / "hga" / "config.json").expanduser()
    try:
        kdir = json.loads(user.read_text(encoding="utf-8")).get("knowledge_dir")
    except (OSError, ValueError, AttributeError):
        kdir = None
    return kdir or "~/.hga/knowledge"


def pages(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        out.append(p)
    return out


def split_frontmatter(text: str) -> tuple[dict[str, str] | None, str, int]:
    """Returns (fields, body, body's first line number). Fields is None if there is no frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, 1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fields: dict[str, str] = {}
            for ln in lines[1:i]:
                if not ln.strip() or ln.lstrip().startswith("#") or ln.startswith((" ", "\t", "-")):
                    continue
                key, sep, val = ln.partition(":")
                if not sep:
                    continue
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                fields[key.strip()] = val
            return fields, "\n".join(lines[i + 1 :]), i + 2
    return None, text, 1


def code_free_lines(body: str, first_line: int = 1):
    """Yields (line number, text) outside fenced code blocks, with inline code removed."""
    in_fence = False
    for k, ln in enumerate(body.splitlines()):
        if FENCE_RE.match(ln):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield first_line + k, INLINE_CODE_RE.sub("", ln)


def wikilinks(body: str) -> list[str]:
    return [m.group(1).strip() for _n, ln in code_free_lines(body) for m in WIKILINK_RE.finditer(ln)]


def issue_refs(text: str) -> set[int]:
    return {int(m.group(1)) for _n, ln in code_free_lines(text) for m in ISSUE_RE.finditer(ln)}
