"""hga issue workflow helper: configuration, repository check, issue status, timestamps, time and token
measurement, bot review requests and waiting, dependencies and triage.

Subcommands (GitHub calls go through the `gh` CLI; standard library only):

  config
      The merged configuration as JSON: defaults < team (`<knowledge_dir>/hga.config.json`) < user
      (`~/.claude/hga/config.json`). Skills and panels read their settings from here.
  doctor
      Checks the prerequisites (Python, git, gh login and scopes, uv, knowledge base, configuration).
      Exit code 1 if a required item is missing.
  midnight
      Today's local midnight as a Unix timestamp (the `oldest` parameter for reading today's Slack
      messages), in the configured time zone.
  now
      The current time in ISO format (to record when the work started).
  repo-check <owner/repo> [--path <dir>]
      Whether the checkout's `origin` remote is the issue's repository. Exits with 4 on a mismatch and
      names the issue repository's checkout if it exists next to this one.
  elapsed <iso-start> [--until <iso>] [--session <id>]... [--pause-min 15]
      Wall-clock time since the start (or until --until). If the session transcript is available, it also
      breaks it down: active time, review wait (idle while a `review-wait` runs), and pauses (idle gaps of
      at least --pause-min minutes outside review waits, plus waits for an AskUserQuestion answer).
  tokens [--since <iso>] [--session <id>]...
      The session's real token use from the transcript's `usage` fields, subagents included, de-duplicated
      by message id: API calls, output, fresh input, cache write, cache read. --since isolates the issue's
      own part of a longer session.
  status <owner/repo> <n>
      The issue's workflow status: on the project board if one is configured, otherwise from labels.
  status-set <owner/repo> <n> {Todo,"In Progress",Done}
      Sets the workflow status and reads it back. With a board: the Status field (option IDs are read from
      the project). Without a board: Todo = no status label, In Progress = the in-progress label,
      Done = the in-review label (the closing label stays the maintainer's).
  track <owner/repo> <n> [--status Todo]
      Adds the issue to the configured board if it is not on it yet, then sets the status. Without a board
      it only sets the status labels.
  meta <owner/repo> <n> [--type T] [--priority P] [--effort E] [--iteration current|<name>]
      The issue type, the Priority and Effort issue fields and the board iteration: sets the given ones,
      then prints them in one line. Fields that do not exist for the owner are reported as n/a.
      Exit code 4 if something did not take effect.
  review-request <owner/repo> <pr> [--provider P]
      Asks the configured review bot for a review (codex: `@codex review` comment; copilot: adds
      @copilot as reviewer; greptile: `@greptileai` comment).
  review-wait <owner/repo> <pr> [--provider P] [--sha <head-sha>] [--timeout-min 30] [--interval 20]
      Waits until the review bot has reviewed the given (or the PR's current) head commit, then prints the
      result, the round number, the severity breakdown and the inline findings. From round
      `review.ask_after_rounds` on, it says to ask the maintainer about closing the review.
      Exit codes: 0 no findings, 1 findings, 2 timeout, 3 the review failed.
  deps <owner/repo> <n>
      The issue's native dependencies: what blocks it (prerequisites) and what it blocks. Read-only.
      Exit code 3 if a prerequisite is still open.
  block <owner/repo> <n> --by <n>[,<n>...]
      Adds "blocked by" edges (the given issues are prerequisites), skips existing ones, reads back.
  triage-state <owner/repo> <n> {ready-for-agent,ready-for-human,needs-info}
      The triage state label: sets it, removes the other two, creates the label in the repo if missing.
  next <owner/repo> [--json]
      The open issues grouped: ready, needs a human, blocked (with prerequisites), needs info, untriaged,
      in progress, in review. Read-only.

The session (`--session`) defaults to the CLAUDE_CODE_SESSION_ID environment variable; transcripts live
in `~/.claude/projects/*/<id>.jsonl` (subagents in `<id>/subagents/*.jsonl`).

Exit code on wrong usage or a gh error: 4.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, tzinfo
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# --- configuration ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "language": "en",
    "timezone": None,
    "github": {
        "project": None,
        "fields": {"status": "Status", "iteration": "Iteration", "priority": "Priority", "effort": "Effort"},
        "statuses": {"todo": "Todo", "in_progress": "In Progress", "done": "Done"},
    },
    "labels": {"in_progress": "in-progress", "in_review": "in-review", "closed": "done"},
    "slack": None,
    "review": {"provider": "local", "ask_after_rounds": 5},
    "parallel": {"max_per_repo": 2, "usage_ceiling_pct": 80},
}

REVIEW_PROVIDERS = ("local", "codex", "copilot", "greptile")


def user_config_path() -> Path:
    env = os.environ.get("HGA_USER_CONFIG")
    return Path(env).expanduser() if env else Path.home() / ".claude" / "hga" / "config.json"


def _read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"not a JSON object: {path}")
    return data


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config() -> dict:
    user_path = user_config_path()
    user = _read_json(user_path)
    kdir = os.environ.get("HGA_KNOWLEDGE_DIR") or user.get("knowledge_dir") or "~/.hga/knowledge"
    kdir_path = Path(kdir).expanduser()
    team_path = kdir_path / "hga.config.json"
    team = _read_json(team_path)
    cfg = _merge(DEFAULTS, team)
    cfg = _merge(cfg, {k: v for k, v in user.items() if k != "knowledge_dir"})
    cfg["knowledge_dir"] = str(kdir_path)
    cfg["sources"] = {
        "team": str(team_path) if team_path.exists() else None,
        "user": str(user_path) if user_path.exists() else None,
    }
    return cfg


CFG: dict = {}


def config_problems(c: dict) -> list[str]:
    """Shape checks for the merged configuration; an empty list means it is usable."""
    out = []
    if not isinstance(c.get("language"), str) or not c["language"]:
        out.append("language must be a language code, e.g. \"en\"")
    gh_ = c.get("github") or {}
    if gh_.get("project") is not None and not isinstance(gh_.get("project"), str):
        out.append("github.project must be a project title or null")
    slack = c.get("slack")
    if slack is not None and not (isinstance(slack, dict) and slack.get("channel_id")):
        out.append("slack must be null or {\"channel\": \"#name\", \"channel_id\": \"C…\"}")
    if (c.get("review") or {}).get("provider") not in REVIEW_PROVIDERS:
        out.append(f"review.provider must be one of {', '.join(REVIEW_PROVIDERS)}")
    par = c.get("parallel") or {}
    for key in ("max_per_repo", "usage_ceiling_pct"):
        if not isinstance(par.get(key), int) or par[key] < 1:
            out.append(f"parallel.{key} must be a positive whole number")
    return out


def cfg() -> dict:
    global CFG
    if not CFG:
        CFG = load_config()
    return CFG


def local_tz() -> tzinfo:
    name = cfg().get("timezone")
    if name and ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:  # unknown zone, or no tz database (Windows without tzdata)
            print(f"warning: unknown time zone {name!r}, using the system's", file=sys.stderr)
    return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def project_name(a) -> str | None:
    return getattr(a, "project", None) or cfg()["github"].get("project")


# --- gh ----------------------------------------------------------------------------------------


def gh(*args: str) -> str:
    res = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}…: {res.stderr.strip()[:400]}")
    return res.stdout


def gql(query: str, **vars_: object) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, v in vars_.items():
        if v is None:
            continue
        args += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    return json.loads(gh(*args))["data"]


def split_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise SystemExit(f"expected owner/repo, got: {repo}")
    owner, name = repo.split("/", 1)
    return owner, name


# --- doctor ------------------------------------------------------------------------------------


def _scopes(status_text: str) -> set[str]:
    m = re.search(r"Token scopes:\s*(.+)", status_text)
    return {s.strip(" '\"") for s in m.group(1).split(",")} if m else set()


def cmd_doctor(_a) -> int:
    c = cfg()
    problems = 0

    def line(ok: bool | None, label: str, detail: str = "") -> None:
        nonlocal problems
        mark = "ok" if ok else ("--" if ok is None else "MISSING")
        if ok is False:
            problems += 1
        print(f"[{mark:>7}] {label}" + (f" · {detail}" if detail else ""))

    line(sys.version_info >= (3, 9), "Python 3.9+", platform.python_version())
    line(shutil.which("git") is not None, "git")
    has_gh = shutil.which("gh") is not None
    line(has_gh, "gh (GitHub CLI)")
    if has_gh:
        res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, encoding="utf-8")
        text = res.stdout + res.stderr
        line(res.returncode == 0, "gh logged in")
        scopes = _scopes(text)
        if scopes:
            line("repo" in scopes, "gh scope: repo", ", ".join(sorted(scopes)))
            if c["github"].get("project"):
                line("project" in scopes, "gh scope: project",
                     "needed for the project board: gh auth refresh -s project")
    line(shutil.which("uv") is not None or None, "uv (optional, live tests of Python apps)")
    if c.get("timezone") and ZoneInfo is not None:
        try:
            ZoneInfo(c["timezone"])
            line(True, f"time zone {c['timezone']}")
        except Exception:
            line(False, f"time zone {c['timezone']}", "on Windows: pip install tzdata")
    kdir = Path(c["knowledge_dir"])
    line(kdir.is_dir(), "knowledge base", str(kdir))
    if kdir.is_dir():
        line((kdir / ".git").exists() or None, "knowledge base is a git repository")
        line((kdir / "hga.config.json").exists(), "team configuration", str(kdir / "hga.config.json"))
    line(c["sources"]["user"] is not None or None, "user configuration", str(user_config_path()))
    provider = (c.get("review") or {}).get("provider")
    line(provider in REVIEW_PROVIDERS, "review provider", str(provider))
    for problem in config_problems(c):
        line(False, "configuration", problem)
    line(None, "Slack", f"channel {c['slack'].get('channel')}" if c.get("slack") else "not configured (GitHub comments)")
    line(None, "project board", c["github"].get("project") or "not configured (status labels)")
    return 1 if problems else 0


# --- repository check --------------------------------------------------------------------------

REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", re.I)


def git(path: str, *args: str) -> str | None:
    res = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, encoding="utf-8")
    return res.stdout.strip() if res.returncode == 0 else None


def cmd_repo_check(a) -> int:
    want = a.repo.lower()
    top = git(a.path, "rev-parse", "--show-toplevel")
    if top is None:
        print(f"not a git checkout: {Path(a.path).resolve()}", file=sys.stderr)
        return 4
    url = git(a.path, "remote", "get-url", "origin") or ""
    m = REMOTE_RE.search(url)
    have = f"{m.group(1)}/{m.group(2)}".lower() if m else None
    if have == want:
        print(f"OK: {top} = {a.repo}")
        return 0
    print(f"MISMATCH: the checkout ({top}) belongs to {have or url or '(no origin)'}, the issue to {a.repo}.")
    sibling = Path(top).parent / split_repo(a.repo)[1]
    if sibling.is_dir():
        print(f"Checkout of the issue's repository: {sibling}")
    print("Do not start: tell the user, and restart from the right checkout.")
    return 4


# --- session transcript ------------------------------------------------------------------------


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=local_tz())


def session_ids(a) -> list[str]:
    ids = list(a.session or [])
    if not ids and os.environ.get("CLAUDE_CODE_SESSION_ID"):
        ids = [os.environ["CLAUDE_CODE_SESSION_ID"]]
    return ids


def session_files(ids: list[str]) -> tuple[list[Path], list[Path]]:
    main: list[Path] = []
    subs: list[Path] = []
    for sid in ids:
        main += sorted(PROJECTS_DIR.glob(f"*/{sid}.jsonl"))
        subs += sorted(PROJECTS_DIR.glob(f"*/{sid}/subagents/*.jsonl"))
    return main, subs


def read_jsonl(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


USAGE_KEYS = (
    ("output_tokens", "output"),
    ("input_tokens", "fresh input"),
    ("cache_creation_input_tokens", "cache write"),
    ("cache_read_input_tokens", "cache read"),
)


def count_tokens(files: list[Path], since: datetime | None) -> dict[str, Counter]:
    seen: set[str] = set()
    per_model: dict[str, Counter] = defaultdict(Counter)
    for f in files:
        for o in read_jsonl(f):
            if o.get("type") != "assistant":
                continue
            m = o.get("message") or {}
            usage, mid, model = m.get("usage"), m.get("id"), m.get("model") or "?"
            if not usage or not mid or mid in seen or model == "<synthetic>":
                continue
            if since and o.get("timestamp") and parse_ts(o["timestamp"]) < since:
                continue
            seen.add(mid)
            per_model[model]["calls"] += 1
            for key, _label in USAGE_KEYS:
                per_model[model][key] += usage.get(key) or 0
    return per_model


def cmd_tokens(a) -> int:
    ids = session_ids(a)
    if not ids:
        print("no session id: pass it with --session", file=sys.stderr)
        return 4
    main, subs = session_files(ids)
    if not main:
        print(f"no transcript for this session: {', '.join(ids)}", file=sys.stderr)
        return 4
    since = parse_ts(a.since) if a.since else None
    per_model = count_tokens(main + subs, since)
    total = sum(per_model.values(), Counter())
    scope = f"since {since.astimezone(local_tz()):%m-%d %H:%M}" if since else "the whole session"
    print(f"Session: {', '.join(ids)} · {len(main)} transcript(s) + {len(subs)} subagent transcript(s) · {scope}")
    if len(per_model) > 1:
        for model, c in sorted(per_model.items(), key=lambda kv: -kv[1]["calls"]):
            row = ", ".join(f"{label} {fmt_tokens(c[key])}" for key, label in USAGE_KEYS)
            print(f"  {model}: {c['calls']} calls · {row}")
    parts = [f"{total['calls']} API calls"] + [f"{label} {fmt_tokens(total[key])}" for key, label in USAGE_KEYS]
    print(f"Report line: {' · '.join(parts)}")
    return 0


# --- elapsed time ------------------------------------------------------------------------------

TOOL_USE_ID_RE = re.compile(r"<tool-use-id>([^<]+)</tool-use-id>")
REVIEW_WAIT_RE = re.compile(r"\breview-wait\b")


def _texts(o: dict) -> list[str]:
    content = (o.get("message") or {}).get("content")
    if isinstance(content, str):
        return [content]
    if isinstance(o.get("content"), str):  # queue-operation
        return [o["content"]]
    if isinstance(content, list):
        return [b.get("text") or "" for b in content if b.get("type") == "text"]
    return []


def _is_human(o: dict) -> bool:
    return (o.get("origin") or {}).get("kind") == "human"


def _is_tool_result(o: dict) -> bool:
    content = (o.get("message") or {}).get("content")
    return isinstance(content, list) and any(b.get("type") == "tool_result" for b in content)


def _overlap(a0: datetime, a1: datetime, spans: list[tuple[datetime, datetime]]) -> float:
    """Seconds shared by [a0, a1] and a list of non-overlapping spans."""
    total = 0.0
    for s0, s1 in spans:
        lo, hi = max(a0, s0), min(a1, s1)
        if hi > lo:
            total += (hi - lo).total_seconds()
    return total


def _union(spans: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for s0, s1 in sorted(spans):
        if out and s0 <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], s1))
        else:
            out.append((s0, s1))
    return out


def _hm(t: datetime) -> str:
    return f"{t.astimezone(local_tz()):%H:%M}"


def breakdown(entries: list[tuple[datetime, dict]], start: datetime, now: datetime, pause_min: float) -> dict:
    """Splits the wall-clock time between start and now into active time, review wait and pauses."""
    wait_open: dict[str, tuple[datetime, bool]] = {}
    ask_open: dict[str, datetime] = {}
    wait_spans: list[tuple[datetime, datetime]] = []
    ask_spans: list[tuple[datetime, datetime]] = []
    for t, o in entries:
        content = (o.get("message") or {}).get("content")
        if o.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if b.get("type") != "tool_use":
                    continue
                inp = b.get("input") or {}
                if b.get("name") in ("Bash", "PowerShell") and REVIEW_WAIT_RE.search(inp.get("command") or ""):
                    wait_open[b["id"]] = (t, bool(inp.get("run_in_background")))
                elif b.get("name") == "AskUserQuestion":
                    ask_open[b["id"]] = t
            continue
        if isinstance(content, list):
            for b in content:
                if b.get("type") != "tool_result":
                    continue
                tid = b.get("tool_use_id")
                if tid in ask_open:
                    ask_spans.append((ask_open.pop(tid), t))
                elif tid in wait_open and not wait_open[tid][1]:
                    wait_spans.append((wait_open.pop(tid)[0], t))
        # A background review-wait ends with the task notification, which carries the tool-use id
        for txt in _texts(o):
            for tid in TOOL_USE_ID_RE.findall(txt):
                if tid in wait_open:
                    wait_spans.append((wait_open.pop(tid)[0], t))
    wait_spans += [(t0, now) for t0, _bg in wait_open.values()]
    wait_runs = len(wait_spans)
    wait_spans = _union(wait_spans)
    ask_spans = _union(ask_spans)

    wall = (now - start).total_seconds()
    review_idle = 0.0
    pause = 0.0
    pauses: list[tuple[datetime, datetime, float, str]] = []
    timeline = entries + [(now, {})]
    for i in range(len(timeline) - 1):
        t0, t1 = timeline[i][0], timeline[i + 1][0]
        gap = (t1 - t0).total_seconds()
        if gap < 60:
            continue
        in_wait = _overlap(t0, t1, wait_spans)
        review_idle += in_wait
        rest = gap - in_wait
        asking = _overlap(t0, t1, ask_spans) > 0
        if rest <= 0 or (rest < pause_min * 60 and not asking):
            continue
        pause += rest
        soon = [o for t, o in timeline[i + 1 : i + 6] if o and (t - t1) <= timedelta(minutes=2)]
        if asking:
            why = "waiting for an AskUserQuestion answer"
        elif any(_is_human(o) for o in soon):
            why = "ended by a user message"
        elif _is_tool_result(timeline[i + 1][1]):
            why = "tool run or waiting for permission"
        else:
            why = "other"
        pauses.append((t0, t1, rest, why))
    return {
        "wall": wall,
        "active": max(0.0, wall - review_idle - pause),
        "review_idle": review_idle,
        "review_runs": wait_runs,
        "pause": pause,
        "pauses": pauses,
    }


def cmd_elapsed(a) -> int:
    start = parse_ts(a.start)
    now = parse_ts(a.until) if a.until else datetime.now(local_tz())
    wall = (now - start).total_seconds()
    head = f"{round(wall / 60)} min ({_hm(start)}–{_hm(now)})"
    ids = session_ids(a)
    main = session_files(ids)[0] if ids else []
    if not main:
        print(f"Wall clock: {head}")
        print("(the session transcript was not found, so only the wall-clock time is known)")
        print(f"Report line: {head}")
        return 0

    entries: list[tuple[datetime, dict]] = []
    for f in main:
        for o in read_jsonl(f):
            if o.get("type") not in ("user", "assistant", "queue-operation") or not o.get("timestamp"):
                continue
            t = parse_ts(o["timestamp"])
            if start <= t <= now:
                entries.append((t, o))
    entries.sort(key=lambda e: e[0])
    b = breakdown(entries, start, now, a.pause_min)

    print(f"Wall clock: {head}")
    print(f"Active: {round(b['active'] / 60)} min")
    print(f"Review wait: {round(b['review_idle'] / 60)} min ({b['review_runs']} review-wait run(s))")
    print(f"Pauses: {round(b['pause'] / 60)} min")
    for t0, t1, secs, why in b["pauses"]:
        print(f"  - {_hm(t0)}–{_hm(t1)} · {round(secs / 60)} min · {why}")
    tail = f"; active {round(b['active'] / 60)}, review wait {round(b['review_idle'] / 60)}"
    if b["pause"]:
        spans = ", ".join(f"{_hm(t0)}–{_hm(t1)}" for t0, t1, _s, _w in b["pauses"])
        tail += f", pauses {round(b['pause'] / 60)} ({spans})"
    print(f"Report line: {head}{tail} min")
    return 0


# --- workflow status: project board or labels ----------------------------------------------------

ITEMS_Q = """
query($owner:String!,$name:String!,$num:Int!,$field:String!){repository(owner:$owner,name:$name){
  issue(number:$num){ id state stateReason title labels(first:30){nodes{name}} projectItems(first:10){nodes{
    id project{id number title}
    fieldValueByName(name:$field){... on ProjectV2ItemFieldSingleSelectValue{name optionId}}
  }}}}}
"""

FIELD_Q = """
query($pid:ID!,$field:String!){node(id:$pid){... on ProjectV2{field(name:$field){
  ... on ProjectV2SingleSelectField{id options{id name}}}}}}
"""

PROJECTS_Q = """
query($owner:String!){repositoryOwner(login:$owner){
  ... on ProjectV2Owner{projectsV2(first:50){nodes{id number title}}}}}
"""

CANONICAL = {"todo": "todo", "in progress": "in_progress", "in_progress": "in_progress", "done": "done"}


def canonical_status(s: str) -> str:
    key = CANONICAL.get(s.strip().lower())
    if key is None:
        raise SystemExit(f"unknown status: {s} (use Todo, \"In Progress\" or Done)")
    return key


def status_field() -> str:
    return cfg()["github"]["fields"]["status"]


def issue_items(repo: str, num: int) -> dict:
    owner, name = split_repo(repo)
    issue = gql(ITEMS_Q, owner=owner, name=name, num=num, field=status_field())["repository"]["issue"]
    if issue is None:
        raise SystemExit(f"no such issue: {repo}#{num}")
    return issue


def label_names(issue: dict) -> set[str]:
    return {x["name"] for x in ((issue.get("labels") or {}).get("nodes") or [])}


def label_status(labels: set[str]) -> str:
    lab = cfg()["labels"]
    if lab["in_review"] in labels:
        return "Done"
    if lab["in_progress"] in labels:
        return "In Progress"
    return "Todo"


def ensure_label(repo: str, name: str, color: str, desc: str, existing: set[str] | None = None) -> None:
    if existing is None:
        existing = {x["name"] for x in json.loads(gh("label", "list", "--repo", repo, "--limit", "500", "--json", "name"))}
    if name not in existing:
        gh("label", "create", name, "--repo", repo, "--color", color, "--description", desc)


def cmd_status(a) -> int:
    issue = issue_items(a.repo, a.num)
    project = project_name(a)
    print(f"{a.repo}#{a.num}: {issue['title']}")
    print(f"  issue state: {issue['state']}" + (f" ({issue['stateReason']})" if issue.get("stateReason") else ""))
    labels = label_names(issue)
    if cfg()["labels"]["closed"] in labels:
        print(f"  closing label: {cfg()['labels']['closed']} (closed by the maintainer)")
    if not project:
        print(f"  Status: {label_status(labels)} (labels; no project board configured)")
        return 0
    nodes = issue["projectItems"]["nodes"]
    if not any(n["project"]["title"] == project for n in nodes):
        print(f"  (not on the \"{project}\" board — add it with: track)")
    for n in nodes:
        st = (n.get("fieldValueByName") or {}).get("name", "—")
        print(f"  board: {n['project']['title']} (#{n['project']['number']}) · Status: {st} · item: {n['id']}")
    return 0


def set_label_status(repo: str, num: int, status: str) -> int:
    lab = cfg()["labels"]
    want = {"todo": None, "in_progress": lab["in_progress"], "done": lab["in_review"]}[status]
    existing = {x["name"] for x in json.loads(gh("label", "list", "--repo", repo, "--limit", "500", "--json", "name"))}
    if want:
        desc = "Being implemented (hga)" if status == "in_progress" else "Implemented, waiting for the maintainer (hga)"
        ensure_label(repo, want, "1d76db" if status == "in_progress" else "5319e7", desc, existing)
    args = ["issue", "edit", str(num), "--repo", repo]
    if want:
        args += ["--add-label", want]
    for other in (lab["in_progress"], lab["in_review"]):
        if other != want and other in existing:
            args += ["--remove-label", other]
    if len(args) > 5:
        gh(*args)
    after = issue_items(repo, num)
    st = label_status(label_names(after))
    print(f"{repo}#{num} · Status: {st} (labels) · issue: {after['state']}")
    return 0 if canonical_status(st) == status else 4


def cmd_status_set(a) -> int:
    status = canonical_status(a.status)
    project = project_name(a)
    if not project:
        return set_label_status(a.repo, a.num, status)
    issue = issue_items(a.repo, a.num)
    nodes = [n for n in issue["projectItems"]["nodes"] if n["project"]["title"] == project]
    if not nodes:
        print(f"the issue is not on the \"{project}\" board — add it first (track)", file=sys.stderr)
        return 4
    item = nodes[0]
    field = gql(FIELD_Q, pid=item["project"]["id"], field=status_field())["node"]["field"]
    if not field:
        print(f"no single-select \"{status_field()}\" field on \"{project}\"", file=sys.stderr)
        return 4
    want = cfg()["github"]["statuses"][status]
    opts = {o["name"].lower(): o["id"] for o in field["options"]}
    opt = opts.get(want.lower())
    if not opt:
        print(f"unknown status: {want} (available: {', '.join(o['name'] for o in field['options'])})", file=sys.stderr)
        return 4
    gh(
        "project", "item-edit", "--id", item["id"], "--project-id", item["project"]["id"],
        "--field-id", field["id"], "--single-select-option-id", opt,
    )
    after = issue_items(a.repo, a.num)
    st = next(
        ((n.get("fieldValueByName") or {}).get("name") for n in after["projectItems"]["nodes"] if n["id"] == item["id"]),
        None,
    )
    print(f"{a.repo}#{a.num} · {project} · Status: {st} · issue: {after['state']}")
    return 0 if (st or "").lower() == want.lower() else 4


def cmd_track(a) -> int:
    project = project_name(a)
    if project:
        issue = issue_items(a.repo, a.num)
        if not any(n["project"]["title"] == project for n in issue["projectItems"]["nodes"]):
            owner, _name = split_repo(a.repo)
            node = gql(PROJECTS_Q, owner=owner).get("repositoryOwner") or {}
            projects = (node.get("projectsV2") or {}).get("nodes", [])
            proj = next((p for p in projects if p["title"] == project), None)
            if proj is None:
                print(f"no \"{project}\" project for {owner}", file=sys.stderr)
                return 4
            gh(
                "project", "item-add", str(proj["number"]), "--owner", owner,
                "--url", f"https://github.com/{a.repo}/issues/{a.num}",
            )
    return cmd_status_set(a)


# --- issue metadata: type, Priority / Effort, iteration ------------------------------------------

META_Q = """
query($owner:String!,$name:String!,$num:Int!,$field:String!){repository(owner:$owner,name:$name){issue(number:$num){
  id title issueType{name}
  issueFieldValues(first:20){nodes{... on IssueFieldSingleSelectValue{name field{... on IssueFieldSingleSelect{name}}}}}
  projectItems(first:10){nodes{id project{id title}
    fieldValueByName(name:$field){... on ProjectV2ItemFieldIterationValue{title iterationId}}}}
}}}
"""

META_BASIC_Q = """
query($owner:String!,$name:String!,$num:Int!,$field:String!){repository(owner:$owner,name:$name){issue(number:$num){
  id title issueType{name}
  projectItems(first:10){nodes{id project{id title}
    fieldValueByName(name:$field){... on ProjectV2ItemFieldIterationValue{title iterationId}}}}
}}}
"""

ORG_META_Q = """
query($owner:String!){organization(login:$owner){
  issueTypes(first:20){nodes{id name}}
  issueFields(first:20){nodes{... on IssueFieldSingleSelect{id name options{id name}}}}
}}
"""

ORG_TYPES_Q = """
query($owner:String!){organization(login:$owner){issueTypes(first:20){nodes{id name}}}}
"""

ITERATION_Q = """
query($pid:ID!,$field:String!){node(id:$pid){... on ProjectV2{field(name:$field){
  ... on ProjectV2IterationField{id configuration{iterations{id title startDate duration}}}}}}}
"""


def issue_meta(repo: str, num: int) -> dict:
    """The issue with its type, issue fields and iteration; issue fields are optional (not every owner has them)."""
    owner, name = split_repo(repo)
    field = cfg()["github"]["fields"]["iteration"]
    try:
        issue = gql(META_Q, owner=owner, name=name, num=num, field=field)["repository"]["issue"]
    except RuntimeError:
        issue = gql(META_BASIC_Q, owner=owner, name=name, num=num, field=field)["repository"]["issue"]
        if issue is not None:
            issue["issueFieldValues"] = None
    if issue is None:
        raise SystemExit(f"no such issue: {repo}#{num}")
    return issue


def meta_line(repo: str, num: int, issue: dict, project: str | None) -> dict[str, str]:
    names = cfg()["github"]["fields"]
    if issue.get("issueFieldValues") is None:
        fields: dict = {}
        no_fields = True
    else:
        fields = {
            (v.get("field") or {}).get("name"): v.get("name")
            for v in issue["issueFieldValues"]["nodes"] if v.get("name")
        }
        no_fields = False
    item = next((n for n in issue["projectItems"]["nodes"] if n["project"]["title"] == project), None) if project else None
    it = (item or {}).get("fieldValueByName") or {}
    got = {
        "type": (issue.get("issueType") or {}).get("name") or "—",
        "priority": "n/a" if no_fields else fields.get(names["priority"]) or "—",
        "effort": "n/a" if no_fields else fields.get(names["effort"]) or "—",
        "iteration": "n/a" if not project else it.get("title") or ("—" if item else "not on the board"),
    }
    print(f"{repo}#{num} · Type: {got['type']} · Priority: {got['priority']} · Effort: {got['effort']}"
          f" · Iteration: {got['iteration']}")
    return got


def current_iteration(iterations: list[dict], today=None) -> dict | None:
    today = today or datetime.now(local_tz()).date()
    for it in iterations:
        start = datetime.strptime(it["startDate"], "%Y-%m-%d").date()
        if start <= today < start + timedelta(days=it["duration"]):
            return it
    return None


def cmd_meta(a) -> int:
    issue = issue_meta(a.repo, a.num)
    owner, _name = split_repo(a.repo)
    project = project_name(a)
    names = cfg()["github"]["fields"]
    want: dict[str, str] = {}
    if a.type or a.priority or a.effort:
        try:
            org = gql(ORG_META_Q, owner=owner).get("organization")
        except RuntimeError:
            org = gql(ORG_TYPES_Q, owner=owner).get("organization") if a.type else None
        if org is None:
            print(f"{owner} is not an organization: issue types and issue fields are not available", file=sys.stderr)
            return 4
        if a.type:
            types = {t["name"].lower(): t for t in org["issueTypes"]["nodes"]}
            t = types.get(a.type.lower())
            if t is None:
                print(f"unknown type: {a.type} (available: {', '.join(x['name'] for x in types.values()) or 'none'})",
                      file=sys.stderr)
                return 4
            gql("mutation($i:ID!,$t:ID!){updateIssueIssueType(input:{issueId:$i,issueTypeId:$t}){issue{id}}}",
                i=issue["id"], t=t["id"])
            want["type"] = t["name"]
        fields = {f["name"]: f for f in ((org.get("issueFields") or {}).get("nodes") or []) if f.get("name")}
        values = []
        for key, val in (("priority", a.priority), ("effort", a.effort)):
            if not val:
                continue
            f = fields.get(names[key])
            opt = next((o for o in (f or {}).get("options", []) if o["name"].lower() == val.lower()), None)
            if opt is None:
                have = ", ".join(o["name"] for o in (f or {}).get("options", []))
                print(f"unknown {names[key]}: {val} (available: {have or 'no such field'})", file=sys.stderr)
                return 4
            values.append(f'{{fieldId:{json.dumps(f["id"])},singleSelectOptionId:{json.dumps(opt["id"])}}}')
            want[key] = opt["name"]
        if values:
            gql(f"mutation($i:ID!){{setIssueFieldValue(input:{{issueId:$i,issueFields:[{','.join(values)}]}}){{issue{{id}}}}}}",
                i=issue["id"])
    if a.iteration:
        if not project:
            print("no project board configured: iterations are not available", file=sys.stderr)
            return 4
        item = next((n for n in issue["projectItems"]["nodes"] if n["project"]["title"] == project), None)
        if item is None:
            print(f"the issue is not on the \"{project}\" board — first: track", file=sys.stderr)
            return 4
        field = gql(ITERATION_Q, pid=item["project"]["id"], field=names["iteration"])["node"]["field"]
        if not field:
            print(f"no iteration field \"{names['iteration']}\" on \"{project}\"", file=sys.stderr)
            return 4
        its = field["configuration"]["iterations"]
        it = current_iteration(its) if a.iteration == "current" else next((x for x in its if x["title"] == a.iteration), None)
        if it is None:
            print(f"no such iteration: {a.iteration} (available: {', '.join(x['title'] for x in its)})", file=sys.stderr)
            return 4
        gh("project", "item-edit", "--id", item["id"], "--project-id", item["project"]["id"],
           "--field-id", field["id"], "--iteration-id", it["id"])
        want["iteration"] = it["title"]
    got = meta_line(a.repo, a.num, issue_meta(a.repo, a.num), project)
    wrong = [k for k, v in want.items() if got.get(k) != v]
    if wrong:
        print(f"did not take effect: {', '.join(wrong)}", file=sys.stderr)
        return 4
    return 0


# --- bot review --------------------------------------------------------------------------------

# Codex: a summary comment tracks the run; findings come as a PR review with inline comments, a clean
# run as an issue comment. Copilot and Greptile submit a PR review per run, tied to the reviewed commit.
PROVIDERS = {
    "codex": {"login": re.compile(r"codex", re.I), "request": ("comment", "@codex review")},
    "copilot": {"login": re.compile(r"copilot", re.I), "request": ("reviewer", "@copilot")},
    "greptile": {"login": re.compile(r"greptile", re.I), "request": ("comment", "@greptileai")},
}

CODEX_SUMMARY_MARK = "codex-pull-request-review-summary"
CODEX_CLEAN_MARK = "Didn't find any major issues"
CODEX_STATUS_RE = re.compile(r"\*\*(Running|Completed|Failed|Error|Cancelled|Canceled|Skipped)\*\*", re.I)
CODEX_SHA_RE = re.compile(r"\|\s*`([0-9a-f]{7,40})`\s*\|")
CODEX_REVIEWED_RE = re.compile(r"\*\*Reviewed commit:\*\*\s*`([0-9a-f]{7,40})`")
PRIO_RES = (
    re.compile(r"!\[(P\d) Badge\]"),
    re.compile(r"\b(P[0-3])\b"),
    re.compile(r"\*\*(critical|high|medium|low|logic|style|syntax)\b", re.I),
)
MARKUP_RE = re.compile(r"</?sub>|\*\*|!\[[^\]]*\]\([^)]*\)")


def provider_of(a) -> str:
    p = (getattr(a, "provider", None) or cfg()["review"].get("provider") or "local").lower()
    if p not in REVIEW_PROVIDERS:
        raise SystemExit(f"unknown review provider: {p} (available: {', '.join(REVIEW_PROVIDERS)})")
    return p


def is_bot(c: dict, provider: str) -> bool:
    return bool(PROVIDERS[provider]["login"].search((c.get("user") or {}).get("login") or ""))


def severity_of(body: str) -> str:
    for rx in PRIO_RES:
        m = rx.search(body)
        if m:
            return m.group(1).upper() if m.group(1).lower().startswith("p") else m.group(1).lower()
    return "—"


def finding_title(body: str) -> str:
    lines = (MARKUP_RE.sub("", ln).strip() for ln in body.splitlines())
    return next((ln for ln in lines if ln), "")


def cmd_review_request(a) -> int:
    provider = provider_of(a)
    if provider == "local":
        print("review provider is local: run the code-review skill, there is no bot to ask")
        return 4
    kind, value = PROVIDERS[provider]["request"]
    if kind == "comment":
        gh("pr", "comment", str(a.pr), "--repo", a.repo, "--body", value)
    else:
        gh("pr", "edit", str(a.pr), "--repo", a.repo, "--add-reviewer", value)
    print(f"review requested from {provider} on {a.repo}#{a.pr} ({value})")
    return 0


def codex_state(repo: str, pr: int) -> tuple[str | None, str | None]:
    comments = json.loads(gh("api", f"repos/{repo}/issues/{pr}/comments", "--paginate"))
    summ = [c for c in comments if is_bot(c, "codex") and CODEX_SUMMARY_MARK in (c.get("body") or "")]
    if not summ:
        return None, None
    body = summ[-1]["body"]
    st = CODEX_STATUS_RE.search(body)
    sha = CODEX_SHA_RE.search(body)
    return (st.group(1).capitalize() if st else None), (sha.group(1) if sha else None)


def bot_reviews(repo: str, pr: int, provider: str) -> list[dict]:
    reviews = json.loads(gh("api", f"repos/{repo}/pulls/{pr}/reviews", "--paginate"))
    return [r for r in reviews if is_bot(r, provider)]


def count_rounds(provider: str, reviews: list[dict], issue_comments: list[dict]) -> int:
    """Completed rounds: the bot's reviews (+ for Codex, its clean-result comments)."""
    if provider == "codex":
        with_findings = [r for r in reviews if CODEX_REVIEWED_RE.search(r.get("body") or "")]
        clean = [c for c in issue_comments if is_bot(c, "codex") and CODEX_CLEAN_MARK in (c.get("body") or "")]
        return len(with_findings) + len(clean)
    return len(reviews)


def wait_codex(a, head: str) -> tuple[int | None, str | None]:
    deadline = time.monotonic() + a.timeout_min * 60
    status = sha = None
    while time.monotonic() < deadline:
        status, sha = codex_state(a.repo, a.pr)
        if status and status != "Running" and sha and head.startswith(sha):
            break
        time.sleep(a.interval)
    else:
        print(f"timeout: codex status={status}, commit={sha}, expected head={head[:7]}")
        return 2, None
    print(f"Review (codex): {status} · commit {sha}")
    return (None if status == "Completed" else 3), sha


def wait_review(a, provider: str, head: str) -> tuple[int | None, dict | None]:
    deadline = time.monotonic() + a.timeout_min * 60
    while time.monotonic() < deadline:
        done = [r for r in bot_reviews(a.repo, a.pr, provider) if (r.get("commit_id") or "").startswith(head[:7])]
        if done:
            r = done[-1]
            print(f"Review ({provider}): {r.get('state', '?').title()} · commit {head[:7]}")
            return None, r
        time.sleep(a.interval)
    print(f"timeout: no {provider} review for head {head[:7]}")
    return 2, None


def cmd_review_wait(a) -> int:
    provider = provider_of(a)
    if provider == "local":
        print("review provider is local: the review is the code-review skill's rounds, there is nothing to wait for")
        return 4
    head = a.sha or json.loads(gh("pr", "view", str(a.pr), "--repo", a.repo, "--json", "headRefOid"))["headRefOid"]
    comments = None
    if provider == "codex":
        code, sha = wait_codex(a, head)
        if code is not None:
            return code
        comments = json.loads(gh("api", f"repos/{a.repo}/issues/{a.pr}/comments", "--paginate"))
        clean = [c for c in comments if is_bot(c, "codex") and CODEX_CLEAN_MARK in (c.get("body") or "")
                 and sha in (c.get("body") or "")]
        # The reviewed commit is kept in original_commit_id; commit_id moves to the new head after a push
        inline = [
            c for c in json.loads(gh("api", f"repos/{a.repo}/pulls/{a.pr}/comments", "--paginate"))
            if is_bot(c, "codex") and (c.get("original_commit_id") or "").startswith(sha)
        ]
        clean_result = bool(clean) and not inline
    else:
        code, review = wait_review(a, provider, head)
        if code is not None:
            return code
        inline = [
            c for c in json.loads(gh("api", f"repos/{a.repo}/pulls/{a.pr}/comments", "--paginate"))
            if c.get("pull_request_review_id") == review["id"]
        ]
        clean_result = not inline
    if comments is None:
        comments = json.loads(gh("api", f"repos/{a.repo}/issues/{a.pr}/comments", "--paginate"))
    rounds = count_rounds(provider, bot_reviews(a.repo, a.pr, provider), comments)
    if clean_result:
        print(f"Round: {rounds} · Result: no significant findings (👍)")
        return 0
    sev = Counter(severity_of(c.get("body") or "") for c in inline)
    sev_txt = ", ".join(f"{p}: {n}" for p, n in sorted(sev.items()))
    print(f"Round: {rounds} · Result: {len(inline)} inline finding(s) ({sev_txt})")
    for c in inline:
        body = c.get("body") or ""
        print(f"- {severity_of(body)} · {c['path']}:{c.get('line') or c.get('original_line')} · id {c['id']}"
              f" · {finding_title(body)[:160]}")
    ask_at = int(cfg()["review"].get("ask_after_rounds") or 5)
    if rounds >= ask_at:
        print(
            f"This is round {rounds}: before fixing, ask the maintainer whether to close the review "
            "(AskUserQuestion, \"Close with a follow-up issue\" recommended — SKILL.md, step 8)."
        )
    return 1


# --- triage: dependencies, state label, the next issue ---------------------------------------------

TRIAGE_LABELS = {
    "ready-for-agent": ("0e8a16", "Triaged: an agent can implement it (hga:triage)"),
    "ready-for-human": ("fbca04", "Triaged: needs a human decision or work (hga:triage)"),
    "needs-info": ("d93f0b", "Triaged: information is missing (hga:triage)"),
}

DEPS_Q = """
query($o:String!,$n:String!,$num:Int!){repository(owner:$o,name:$n){issue(number:$num){
  blockedBy(first:50){nodes{number title state labels(first:20){nodes{name}}}}
  blocking(first:50){nodes{number title state labels(first:20){nodes{name}}}}}}}
"""


def is_done(issue: dict) -> bool:
    """Closed in the workflow's sense: the maintainer's closing label, or the CLOSED state."""
    return issue.get("state") == "CLOSED" or cfg()["labels"]["closed"] in label_names(issue)


NEXT_Q = """
query($o:String!,$n:String!,$after:String,$field:String!){repository(owner:$o,name:$n){
  issues(states:OPEN,first:100,after:$after,orderBy:{field:CREATED_AT,direction:ASC}){
    pageInfo{hasNextPage endCursor}
    nodes{number title labels(first:20){nodes{name}} blockedBy(first:20){nodes{number state labels(first:20){nodes{name}}}}
      projectItems(first:5){nodes{project{title}
        fieldValueByName(name:$field){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}}
"""


def issue_deps(repo: str, num: int) -> dict:
    owner, name = split_repo(repo)
    issue = gql(DEPS_Q, o=owner, n=name, num=num)["repository"]["issue"]
    if issue is None:
        raise SystemExit(f"no such issue: {repo}#{num}")
    return issue


def print_deps(repo: str, num: int, issue: dict) -> list[int]:
    print(f"{repo}#{num}")
    for key, label in (("blockedBy", "Blocked by (prerequisites)"), ("blocking", "Blocks")):
        nodes = issue[key]["nodes"]
        print(f"  {label}: {'' if nodes else '—'}")
        for x in nodes:
            print(f"    #{x['number']} [{'closed' if is_done(x) else 'open'} · {x['state']}] {x['title']}")
    open_blockers = [x["number"] for x in issue["blockedBy"]["nodes"] if not is_done(x)]
    if open_blockers:
        print(f"  OPEN PREREQUISITE: {', '.join(f'#{n}' for n in open_blockers)}")
    return open_blockers


def cmd_deps(a) -> int:
    return 3 if print_deps(a.repo, a.num, issue_deps(a.repo, a.num)) else 0


def cmd_block(a) -> int:
    have = {x["number"] for x in issue_deps(a.repo, a.num)["blockedBy"]["nodes"]}
    for m in a.by:
        if m in have:
            print(f"#{m} is already a prerequisite")
            continue
        blocker_id = json.loads(gh("api", f"repos/{a.repo}/issues/{m}"))["id"]
        gh("api", "-X", "POST", f"repos/{a.repo}/issues/{a.num}/dependencies/blocked_by", "-F", f"issue_id={blocker_id}")
    issue = issue_deps(a.repo, a.num)
    print_deps(a.repo, a.num, issue)
    missing = set(a.by) - {x["number"] for x in issue["blockedBy"]["nodes"]}
    if missing:
        print(f"not added: {', '.join(f'#{n}' for n in sorted(missing))}", file=sys.stderr)
        return 4
    return 0


def cmd_triage_state(a) -> int:
    existing = {x["name"] for x in json.loads(gh("label", "list", "--repo", a.repo, "--limit", "500", "--json", "name"))}
    color, desc = TRIAGE_LABELS[a.state]
    ensure_label(a.repo, a.state, color, desc, existing)
    others = [x for x in TRIAGE_LABELS if x != a.state]
    args = ["issue", "edit", str(a.num), "--repo", a.repo, "--add-label", a.state]
    for x in others:
        if x in existing:
            args += ["--remove-label", x]
    gh(*args)
    labels = [x["name"] for x in json.loads(gh("issue", "view", str(a.num), "--repo", a.repo, "--json", "labels"))["labels"]]
    print(f"{a.repo}#{a.num} labels: {', '.join(labels)}")
    return 0 if a.state in labels and not set(others) & set(labels) else 4


BUCKET_TITLES = {
    "ready": "Ready (ready-for-agent, no open prerequisite)",
    "needs_human": "Needs a human decision or work (ready-for-human)",
    "blocked": "Blocked (open prerequisite)",
    "needs_info": "Needs info (needs-info)",
    "in_progress": "In progress",
    "in_review": "In review (implemented, waiting for the maintainer)",
    "untriaged": "Untriaged (Todo, no state label)",
}


def bucket_issues(issues: list[dict], project: str | None) -> tuple[dict[str, list[dict]], int]:
    """Groups open issues. With a board, only issues on it count (Todo / In Progress / Done); without one,
    the status labels decide."""
    statuses = cfg()["github"]["statuses"]
    lab = cfg()["labels"]
    buckets: dict[str, list[dict]] = {k: [] for k in BUCKET_TITLES}
    off_board = 0
    for i in issues:
        labels = label_names(i)
        if lab["closed"] in labels:
            continue
        if project:
            status = None
            for item in i["projectItems"]["nodes"]:
                if item["project"]["title"] == project:
                    status = (item.get("fieldValueByName") or {}).get("name")
            if status is None:
                off_board += 1
                continue
            norm = {v.lower(): k for k, v in statuses.items()}.get(status.lower())
        else:
            norm = canonical_status(label_status(labels))
        blockers = [b["number"] for b in i["blockedBy"]["nodes"] if not is_done(b)]
        if norm == "in_progress":
            key = "in_progress"
        elif norm == "done":
            key = "in_review"
        elif norm != "todo":
            continue
        elif blockers:
            key = "blocked"
        elif "needs-info" in labels:
            key = "needs_info"
        elif "ready-for-agent" in labels:
            key = "ready"
        elif "ready-for-human" in labels:
            key = "needs_human"
        else:
            key = "untriaged"
        buckets[key].append({"number": i["number"], "title": i["title"], "blockers": blockers})
    return buckets, off_board


def cmd_next(a) -> int:
    owner, name = split_repo(a.repo)
    project = project_name(a)
    issues: list[dict] = []
    after = None
    while True:
        page = gql(NEXT_Q, o=owner, n=name, after=after, field=status_field())["repository"]["issues"]
        issues += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    buckets, off_board = bucket_issues(issues, project)
    # Machine output for the hga plugin's triage panel: the same groups, rows split into fields.
    if a.json:
        print(json.dumps({"repo": a.repo, "project": project, "buckets": buckets, "off_board": off_board},
                         ensure_ascii=False))
        return 0
    for key, title in BUCKET_TITLES.items():
        rows = [
            f"#{r['number']} {r['title']}"
            + (f"  [prerequisites: {', '.join(f'#{n}' for n in r['blockers'])}]" if key == "blocked" else "")
            for r in buckets[key]
        ]
        print(f"{title}: {len(rows)}")
        shown = rows[:10] if key == "untriaged" else rows
        for row in shown:
            print(f"  {row}")
        if len(rows) > len(shown):
            print(f"  … and {len(rows) - len(shown)} more (oldest first)")
    if project:
        print(f"Open, but not on the \"{project}\" board or without status: {off_board}")
    return 0


# --- entry point -------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config")
    sub.add_parser("doctor")
    sub.add_parser("midnight")
    sub.add_parser("now")
    p = sub.add_parser("repo-check")
    p.add_argument("repo")
    p.add_argument("--path", default=".")
    p = sub.add_parser("elapsed")
    p.add_argument("start")
    p.add_argument("--until")
    p.add_argument("--session", action="append")
    p.add_argument("--pause-min", type=float, default=15)
    p = sub.add_parser("tokens")
    p.add_argument("--since")
    p.add_argument("--session", action="append")
    p = sub.add_parser("status")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("--project")
    p = sub.add_parser("status-set")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("status")
    p.add_argument("--project")
    p = sub.add_parser("track")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("--status", default="Todo")
    p.add_argument("--project")
    for name in ("review-request", "review-wait"):
        p = sub.add_parser(name)
        p.add_argument("repo")
        p.add_argument("pr", type=int)
        p.add_argument("--provider", choices=REVIEW_PROVIDERS)
        if name == "review-wait":
            p.add_argument("--sha")
            p.add_argument("--timeout-min", type=float, default=30)
            p.add_argument("--interval", type=float, default=20)
    p = sub.add_parser("deps")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p = sub.add_parser("block")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("--by", required=True, type=lambda s: [int(x.strip().lstrip("#")) for x in s.split(",") if x.strip()])
    p = sub.add_parser("triage-state")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("state", choices=list(TRIAGE_LABELS))
    p = sub.add_parser("meta", help="set and read back type, Priority, Effort, iteration; without options, only print")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("--type", help="Task | Bug | Feature (the owner's issue types)")
    p.add_argument("--priority", help="e.g. Urgent | High | Medium | Low")
    p.add_argument("--effort", help="e.g. High | Medium | Low")
    p.add_argument("--iteration", help="current, or the iteration's name")
    p.add_argument("--project")
    p = sub.add_parser("next")
    p.add_argument("repo")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true", help="machine output (the hga plugin's triage panel)")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "config":
            print(json.dumps(cfg(), ensure_ascii=False, indent=2))
            return 0
        if a.cmd == "midnight":
            now = datetime.now(local_tz())
            print(f"{now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp():.6f}")
            return 0
        if a.cmd == "now":
            print(datetime.now(local_tz()).isoformat(timespec="seconds"))
            return 0
        return {
            "doctor": cmd_doctor,
            "repo-check": cmd_repo_check,
            "elapsed": cmd_elapsed,
            "tokens": cmd_tokens,
            "status": cmd_status,
            "status-set": cmd_status_set,
            "track": cmd_track,
            "meta": cmd_meta,
            "review-request": cmd_review_request,
            "review-wait": cmd_review_wait,
            "deps": cmd_deps,
            "block": cmd_block,
            "triage-state": cmd_triage_state,
            "next": cmd_next,
        }[a.cmd](a)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
