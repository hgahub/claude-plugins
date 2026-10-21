"""The intent.md readiness gate: PASS / WARN / BLOCK, without a model.

    python3 intent_check.py <intent.md> [--json]
    python3 intent_check.py --self-test

Score: 100, minus 45 per error and 20 per warning. BLOCK if there is an error; PASS if there is none and the
score is >= 85; WARN otherwise. Exit code: 0 PASS, 1 WARN, 2 BLOCK. The --json output also gives each section's
coverage (empty | partial | done) for the hga plugin's `mcp__hga__intent` tool.

The `##` headings and the scenario keywords (Given … when … then …) are fixed English markers, whatever
language the body is written in.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from typing import Optional

# The sections that make up the "full picture", by the start of their heading (case and accents ignored).
SECTIONS = {
    "problem": "problem",
    "outcome": "desired outcome",
    "affected": "affected",
    "current": "current state",
    "behavior": "expected behavior",
    "criteria": "acceptance criteria",
    "constraints": "constraints",
    "scope": "out of scope",
}
QUESTIONS = "open questions"
# An unfilled placeholder (an error, not a warning): <...>, TBD, TODO, three dots or ….
PLACEHOLDER = re.compile(r"<[^>\n]+>|\bTBD\b|\bTODO\b|…|\.\.\.")
# Inside `code` or a ``` block only an angle-bracket placeholder counts (`<sha>`, `origin/<default-branch>`), and
# not code itself: an HTML element (`<button>`, `</div>`, `<input type="text">`), a component (`<UserCard />`) or a
# type argument (`List<String>`).
CODE = re.compile(r"```.*?```|`[^`\n]+`", re.S)
ANGLE = re.compile(r"<[^>\n]+>")
TAG = re.compile(r"</?([A-Za-z][\w.-]*)(\s[^>]*)?>")
HTML_ELEMENTS = frozenset("""
    a abbr address area article aside audio b base bdi bdo blockquote body br button canvas caption cite code col
    colgroup data datalist dd del details dfn dialog div dl dt em embed fieldset figcaption figure footer form h1 h2
    h3 h4 h5 h6 head header hgroup hr html i iframe img input ins kbd label legend li link main map mark menu meta
    meter nav noscript object ol optgroup option output p picture pre progress q rp rt ruby s samp script section
    select slot small source span strong style sub summary sup svg table tbody td template textarea tfoot th thead
    time title tr track u ul var video wbr
""".split())


def is_code(span: str, m: re.Match) -> bool:
    if m.start() and (span[m.start() - 1].isalnum() or span[m.start() - 1] == "_"):
        return True
    tag = TAG.fullmatch(m[0])
    return bool(tag) and (
        tag[1].lower() in HTML_ELEMENTS or tag[1][0].isupper() or "=" in (tag[2] or "") or m[0].endswith("/>")
    )


def unfilled(body: str) -> bool:
    if PLACEHOLDER.search(CODE.sub(" ", body)):
        return True
    return any(not is_code(s, m) for s in CODE.findall(body) for m in ANGLE.finditer(s))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def sectioned(text: str) -> dict:
    """## heading → body (without HTML comments)."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, head = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            head = norm(m[1])
            out[head] = []
        elif head is not None:
            out[head].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def find(sec: dict, prefix: str) -> Optional[str]:
    return next((v for k, v in sec.items() if k.startswith(prefix)), None)


def items(body: Optional[str]) -> list:
    return [l for l in (body or "").splitlines() if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", l)]


def check(text: str) -> dict:
    sec = sectioned(text)
    coverage, errors, warnings = {}, [], []
    for key, prefix in SECTIONS.items():
        body = find(sec, prefix)
        coverage[key] = "empty" if not body else "partial" if unfilled(body) else "done"

    if not re.search(r"^#\s+Intent:\s*\S", text, re.M):
        errors.append("E_NO_TITLE: the \"# Intent: <name>\" heading is missing")
    for key, code in (("problem", "E_EMPTY_PROBLEM"), ("outcome", "E_EMPTY_OUTCOME"), ("affected", "E_NO_AFFECTED")):
        if coverage[key] == "empty":
            errors.append(f"{code}: the \"{SECTIONS[key]}\" section is empty")
    criteria = [l for l in items(find(sec, SECTIONS["criteria"])) if re.match(r"^\s*\d+\.", l)]
    if not criteria:
        errors.append("E_NO_CRITERIA: there is no numbered acceptance criterion")
    scenarios = [
        l for l in items(find(sec, SECTIONS["behavior"]))
        if re.search(r"\bwhen\b", l, re.I) and re.search(r"\bthen\b", l, re.I)
    ]
    if not scenarios:
        errors.append("E_NO_SCENARIO: there is no \"Given … when … then …\" scenario")
    open_q = [l for l in items(find(sec, QUESTIONS)) if not re.match(r"^\s*[-*]\s+(none|—|-)\.?\s*$", l, re.I)]
    blocking = [l for l in open_q if "[blocking]" in l.lower()]
    for key, state in coverage.items():
        if state == "partial":
            errors.append(f"E_PLACEHOLDER: an unfilled placeholder in the \"{SECTIONS[key]}\" section")
    if blocking:
        errors.append(f"E_BLOCKING_QUESTION: {len(blocking)} blocking open question(s)")

    if scenarios and not any(re.search(r"edge case", l, re.I) for l in scenarios):
        warnings.append("W_NO_EDGE_CASE: no scenario is marked \"(edge case)\"")
    if scenarios and criteria and len(scenarios) < len(criteria):
        warnings.append(f"W_FEW_SCENARIOS: {len(criteria)} criteria, {len(scenarios)} scenario(s)")
    if coverage["current"] == "empty":
        warnings.append("W_EMPTY_CURRENT: the \"current state\" section is empty")
    elif not re.search(r"\b[0-9a-f]{7,40}\b", find(sec, SECTIONS["current"]) or ""):
        warnings.append("W_CURRENT_WITHOUT_SHA: the current state does not cite a commit SHA")
    if coverage["constraints"] == "empty":
        warnings.append("W_EMPTY_CONSTRAINTS: the \"constraints\" section is empty")
    if coverage["scope"] == "empty":
        warnings.append("W_EMPTY_SCOPE: the \"out of scope\" section is empty")

    score = max(0, 100 - 45 * len(errors) - 20 * len(warnings))
    verdict = "BLOCK" if errors else "PASS" if score >= 85 else "WARN"
    return {
        "verdict": verdict, "score": score, "errors": errors, "warnings": warnings,
        "sections": coverage, "questions": len(open_q),
    }


SAMPLE = """# Intent: Source column in the Excel export

## Problem
The analyst cannot see which row comes from a verified source.

## Desired outcome
A column in the export shows the source.

## Affected users and systems
- analysts; web-app `export_xlsx()`

## Current state
- `export_xlsx()` does not write the source (origin/main `4a81922`)

## Expected behavior
- Given a verified row, when I export, then the column says "DB – verified".
- Given a row without a source, when I export, then the column is empty. (edge case)

## Acceptance criteria
1. The column appears.
2. Without a source it is empty.

## Constraints
- The column order does not change.

## Out of scope
- PDF export.

## Open questions
- Should it be colored? (not blocking)
"""


def self_test() -> None:
    r = check(SAMPLE)
    assert r["verdict"] == "PASS", r
    assert r["questions"] == 1 and set(r["sections"].values()) == {"done"}, r
    r = check(SAMPLE.replace("1. The column appears.\n2. Without a source it is empty.", "").replace("(not blocking)", "[blocking]"))
    assert r["verdict"] == "BLOCK" and any("E_NO_CRITERIA" in e for e in r["errors"]), r
    assert any("E_BLOCKING" in e for e in r["errors"]), r
    r = check(SAMPLE.replace(" (edge case)", "").replace(" (origin/main `4a81922`)", ""))
    assert r["verdict"] == "WARN" and len(r["warnings"]) == 2, r
    r = check(SAMPLE.replace("`4a81922`", "<sha>"))
    assert r["verdict"] == "BLOCK" and r["sections"]["current"] == "partial", r
    r = check(re.sub(r"## (Current state|Constraints)\n- [^\n]+\n", "", SAMPLE))
    assert r["verdict"] == "WARN" and r["score"] == 60, r
    assert {w.split(":")[0] for w in r["warnings"]} == {"W_EMPTY_CURRENT", "W_EMPTY_CONSTRAINTS"}, r
    assert check(SAMPLE.replace("- Should it be colored? (not blocking)", "- none"))["questions"] == 0
    r = check(SAMPLE.replace("The column appears.", "The `<button>` and `List<Row>` render; `fn(...)` stays."))
    assert r["verdict"] == "PASS", r
    r = check(SAMPLE.replace("`4a81922`", "`<sha>`"))
    assert r["verdict"] == "BLOCK" and r["sections"]["current"] == "partial", r
    print("self-test OK")


def main(argv: Optional[list] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:] if argv is None else argv
    if args == ["--self-test"]:
        self_test()
        return 0
    if not args or args[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 64
    with open(args[0], encoding="utf-8") as f:
        r = check(f.read())
    if "--json" in args:
        print(json.dumps(r, ensure_ascii=False))
    else:
        print(f"{r['verdict']} ({r['score']}) · {r['questions']} open question(s)")
        for s in r["errors"] + r["warnings"]:
            print(f"  {s}")
    return {"PASS": 0, "WARN": 1, "BLOCK": 2}[r["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
