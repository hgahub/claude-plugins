"""hga issue workflow helper: configuration, repository check, issue status, timestamps, time and token
measurement, bot review requests and waiting, dependencies and triage.

Subcommands (GitHub calls go through the `gh` CLI; standard library only):

  config
      The merged configuration as JSON: defaults < team (`<knowledge_dir>/hga.config.json`) < user
      (`~/.claude/hga/config.json`). Skills and panels read their settings from here. Shape problems go to
      stderr as warnings (doctor counts them as missing items).
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
  tokens [--since <iso>] [--until <iso>] [--session <id>]...
      The session's real token use from the transcript's `usage` fields, subagents included, de-duplicated
      by message id: API calls, output, fresh input, cache write, cache read. --since and --until isolate the
      issue's own part of a longer session (--until is exclusive).
  metrics-start <owner/repo> <n> [--session <id>]...
      Writes the run's start marker (`"stage": "started"`, schema 1) once the claim holds, at the path the
      run's record will have (below), and prints it. The record replaces it at step 12; a marker never
      replaced is an aborted run. An existing record of the run is left alone.
  metrics-record <owner/repo> <n> [--difficulty easy|medium|hard] [--review-rounds N] [--risk low|standard|high]
                 [--until <iso>] [--session <id>]... [--pause-min 15]
      Writes the issue's durable metrics record into the knowledge base and prints its path:
      `<knowledge_dir>/metrics/<owner>/<repo>/<n>-<start, UTC>.json`, one file per run of the issue (a later
      run starts later), so parallel sessions never touch the same file. It reads the issue pane's state
      file (`~/.claude/hga/issue/<owner>-<repo>-<n>.json`) for the start, the step times and the five-hour
      usage snapshots, and the transcripts for the elapsed breakdown, the tokens (in total, per section of
      the checklist and per model). The end is --until, else step 12's end, else now. The sessions are the
      --session ones, else this session and the one in the state file. The schema is in the knowledge
      base's metrics/README.md.
  metrics [--repo <owner/repo>] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--format json|csv] [--cost]
          [--stale-hours 24]
      Every schema-1 metrics record of the knowledge base as flat rows for charts (records with another
      schema are skipped with a warning): `kind` = `run` (one per run: elapsed, tokens, the account's
      five-hour usage at start and end), `section` (one per run and section: Prepare, Build, Review,
      Finish) and `model` (one per run, section and model: tokens). --since/--until filter on the run's
      start date (both inclusive). `outcome` on every row: `finished` / `unfinished` (a record), `aborted`
      (only the start marker, older than --stale-hours), `open` (a younger marker), empty for records from
      before the markers; `risk` and `na_steps` (steps reported not_applicable) on every row of a record.
      stderr gets the counts and the abort rate. --cost adds `api_cost_usd_est` to every row: the tokens at Anthropic API
      list prices (a table in this script), an estimate, not what a Claude subscription costs.
  status <owner/repo> <n>
      The issue's workflow status: on the project board if one is configured, otherwise from labels.
  status-set <owner/repo> <n> {Todo,"In Progress",Done}
      Sets the workflow status and reads it back. With a board: the Status field (option IDs are read from
      the project). Without a board: Todo = no status label, In Progress = the in-progress label,
      Done = the in-review label. Closing is GitHub's own: the PR's closing keyword at merge, or
      `gh issue close`.
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
      Copilot and Greptile: only the bot's submitted reviews of that exact commit count (a dismissed one does
      not); requested changes without inline comments are findings too, printed from the review's body.
      Exit codes: 0 no findings, 1 findings, 2 timeout, 3 the review failed.
  claim-check <owner/repo> <n> [--verb V] [--since <unix|iso>]
      Before the claim: whether the issue is free — taken (exit 5) if its workflow status is In Progress
      (Done too, unless --verb is verify / re-verify), it is assigned to another GitHub account, or another
      session posted a `Claimed · …` comment in the last 24 hours. These GitHub signals do not depend on
      the Slack read's window. It prints this session's tag (the claim line carries it) and `Read back
      from`: the start of the read-back window. After the claim, with --since = that value: the read-back
      — it waits a few seconds, then the earliest `Claimed · …` comment since then wins (exit 0); if
      another session's came first, this one withdraws (exit 5). Exit 4 if this session's claim is missing.
  risk <owner/repo> (--worktree <dir> [--base <ref>] | --pr <n>) [--issue <n>] [--json]
      The change's risk class, from its changed files and the team's patterns (`risk.*`): `high` if any
      file matches a high pattern or the issue / PR has the `risk.high_label` label; `low` if every file
      matches a low pattern; `standard` otherwise. A repository's `risk.repos.<owner/repo>` replaces the
      low patterns and adds high ones. --worktree: the worktree's changes since its merge base with --base
      (default: origin's default branch), committed or not, untracked files included; --pr: the PR's
      files. Prints the class, each file's match and the gates the class changes: the evidence of a
      not_applicable step. Exit 4 if there is no changed file.
  deps <owner/repo> <n>
      The issue's native dependencies: what blocks it (prerequisites) and what it blocks. Read-only.
      Exit code 3 if a prerequisite is still open.
  block <owner/repo> <n> --by <n>[,<n>...]
      Adds "blocked by" edges (the given issues are prerequisites), skips existing ones, reads back.
  triage-state <owner/repo> <n> {ready-for-agent,ready-for-human,needs-info}
      The triage state label: sets it, removes the other two, creates the label in the repo if missing.
  next <owner/repo> [--json]
      The open issues grouped: ready, needs a human, blocked (with prerequisites), needs info, untriaged,
      in progress, in review, each with its assignees. Read-only.

The session (`--session`) defaults to the CLAUDE_CODE_SESSION_ID environment variable; transcripts live
in `~/.claude/projects/*/<id>.jsonl` (subagents in `<id>/subagents/*.jsonl`).

Exit code on wrong usage or a gh error: 4.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, tzinfo
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
    "labels": {"in_progress": "in-progress", "in_review": "in-review"},
    "slack": None,
    "review": {"provider": "local", "ask_after_rounds": 5},
    "parallel": {"max_per_repo": 2, "usage_ceiling_pct": 80},
    # The risk classes' file patterns (HGA risk). A pattern without "/" matches the file name anywhere; with "/",
    # the path from the repository root ("**" spans folders). A team's list replaces the default one; per
    # repository, `repos.<owner/repo>.low_paths` replaces the team's list, `high_paths` adds to it.
    "risk": {
        "low_paths": ["*.md", "*.mdx", "*.rst", "*.txt", "docs/**", "LICENSE", "LICENSE.*", "tests/**", "test/**"],
        "high_paths": ["**/migrations/**", "*.sql", "**/auth/**", "**/permissions/**", ".github/workflows/**"],
        "high_label": "risk:high",
        "repos": {},
    },
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


def _text(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _positive_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def config_problems(c: dict) -> list[str]:
    """Shape checks for the merged configuration; an empty list means it is usable. Whether a named time zone
    exists is doctor's own line (it depends on the machine's tz database, not on the file)."""
    out = []
    if not _text(c.get("language")):
        out.append("language must be a language code, e.g. \"en\"")
    if c.get("timezone") is not None and not _text(c.get("timezone")):
        out.append("timezone must be an IANA name, e.g. \"Europe/Berlin\", or null")
    gh_ = c.get("github") or {}
    if gh_.get("project") is not None and not isinstance(gh_.get("project"), str):
        out.append("github.project must be a project title or null")
    if not _text((gh_.get("fields") or {}).get("status")):
        out.append("github.fields.status must name the board's status field, e.g. \"Status\"")
    statuses = gh_.get("statuses") or {}
    for key in ("todo", "in_progress", "done"):
        if not _text(statuses.get(key)):
            out.append(f"github.statuses.{key} must name a status option, e.g. \"{DEFAULTS['github']['statuses'][key]}\"")
    labels = c.get("labels") or {}
    for key in ("in_progress", "in_review"):
        if not _text(labels.get(key)):
            out.append(f"labels.{key} must be a label name, e.g. \"{DEFAULTS['labels'][key]}\"")
    slack = c.get("slack")
    if slack is not None and not (isinstance(slack, dict) and slack.get("channel_id")):
        out.append("slack must be null or {\"channel\": \"#name\", \"channel_id\": \"C…\"}")
    review = c.get("review") or {}
    if review.get("provider") not in REVIEW_PROVIDERS:
        out.append(f"review.provider must be one of {', '.join(REVIEW_PROVIDERS)}")
    if not _positive_int(review.get("ask_after_rounds")):
        out.append("review.ask_after_rounds must be a positive whole number")
    par = c.get("parallel") or {}
    for key in ("max_per_repo", "usage_ceiling_pct"):
        if not _positive_int(par.get(key)):
            out.append(f"parallel.{key} must be a positive whole number")
    risk = c.get("risk") or {}
    for key in ("low_paths", "high_paths"):
        if not _patterns(risk.get(key)):
            out.append(f"risk.{key} must be a list of file patterns, e.g. [\"docs/**\"]")
    if not _text(risk.get("high_label")):
        out.append("risk.high_label must be a label name, e.g. \"risk:high\"")
    repos = risk.get("repos")
    if not isinstance(repos, dict):
        out.append("risk.repos must be an object: {\"owner/repo\": {\"low_paths\": […], \"high_paths\": […]}}")
    else:
        for repo, over in repos.items():
            if not isinstance(over, dict) or not all(_patterns(over[k]) for k in ("low_paths", "high_paths") if k in over):
                out.append(f"risk.repos.{repo} must be an object with low_paths / high_paths lists of file patterns")
    return out


def _patterns(v: object) -> bool:
    return isinstance(v, list) and all(_text(x) for x in v)


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
    # Before /hga:init has run, a missing knowledge base and configuration are expected, not errors.
    set_up = c["sources"]["user"] is not None or kdir.is_dir()
    if not set_up:
        line(None, "knowledge base", f"not set up yet — run /hga:init ({kdir})")
    else:
        line(kdir.is_dir(), "knowledge base", str(kdir))
    if kdir.is_dir():
        has_remote = bool(git(str(kdir), "remote"))
        line((kdir / ".git").exists() or None, "knowledge base is a git repository",
             "with a remote" if has_remote else "local only (no remote)")
        line((kdir / "hga.config.json").exists(), "team configuration", str(kdir / "hga.config.json"))
    line(c["sources"]["user"] is not None or None, "user configuration",
         str(user_config_path()) if set_up else "not set up yet — run /hga:init")
    provider = (c.get("review") or {}).get("provider")
    line(provider in REVIEW_PROVIDERS, "review provider", str(provider))
    for problem in config_problems(c):
        line(False, "configuration", problem)
    if "closed" in (c.get("labels") or {}):
        line(None, "labels.closed", "no longer used (issues close with GitHub's own closing) — remove it from the config")
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


def count_tokens(files: list[Path], since: datetime | None, until: datetime | None = None) -> dict[str, Counter]:
    """Token use per model in [since, until), each API response once (subagent transcripts repeat ids)."""
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
            if (since or until) and o.get("timestamp"):
                t = parse_ts(o["timestamp"])
                if (since and t < since) or (until and t >= until):
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
    until = parse_ts(a.until) if a.until else None
    per_model = count_tokens(main + subs, since, until)
    total = sum(per_model.values(), Counter())
    bounds = []
    if since:
        bounds.append(f"since {since.astimezone(local_tz()):%m-%d %H:%M}")
    if until:
        bounds.append(f"until {until.astimezone(local_tz()):%m-%d %H:%M}")
    scope = " ".join(bounds) or "the whole session"
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
    # The start is on the timeline too: a section's window can open long before its first message.
    timeline = [(start, {})] + entries + [(now, {})]
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


def timeline_entries(main: list[Path], start: datetime, end: datetime) -> list[tuple[datetime, dict]]:
    """The main transcripts' messages between start and end, in time order (the input of breakdown)."""
    entries: list[tuple[datetime, dict]] = []
    for f in main:
        for o in read_jsonl(f):
            if o.get("type") not in ("user", "assistant", "queue-operation") or not o.get("timestamp"):
                continue
            t = parse_ts(o["timestamp"])
            if start <= t <= end:
                entries.append((t, o))
    entries.sort(key=lambda e: e[0])
    return entries


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

    b = breakdown(timeline_entries(main, start, now), start, now, a.pause_min)

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


# --- metrics record ------------------------------------------------------------------------------

ISSUE_DIR = Path.home() / ".claude" / "hga" / "issue"
METRICS_SCHEMA = 1
# The issue pane's checklist and sections (hooks/issue-pane.tsx: STEPS, SECTIONS); keep them in step.
STEP_NAMES = (
    "Start", "Claim", "In Progress", "Worktree", "Decisions", "Build + tests",
    "Live test", "PR", "Review", "Done", "Cleanup", "Knowledge", "Report",
)
SECTIONS = (("Prepare", 0, 4), ("Build", 5, 6), ("Review", 7, 8), ("Finish", 9, 12))
DIFFICULTIES = ("easy", "medium", "hard")


def state_file(repo: str, num: int) -> Path:
    """The issue pane's state file; the name is the pane's: owner/repo#n with every other character run as `-`."""
    return ISSUE_DIR / (re.sub(r"[^A-Za-z0-9_-]+", "-", f"{repo}#{num}") + ".json")


def _ms(v: object) -> datetime | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return datetime.fromtimestamp(v / 1000, local_tz())
    return None


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(local_tz()).isoformat(timespec="seconds") if t else None


def _token_fields(c: Counter) -> dict[str, int]:
    return {"calls": c["calls"], **{key: c[key] for key, _label in USAGE_KEYS}}


def _tokens(per_model: dict[str, Counter]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """(total, per model) in the record's shape: the API's own usage field names."""
    total = sum(per_model.values(), Counter())
    return _token_fields(total), {m: _token_fields(c) for m, c in sorted(per_model.items())}


def section_bounds(steps: list, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Splits [start, end] into one window per section, without gaps or overlaps, so the sections' tokens add
    up to the total. A section starts at its earliest step time; a section without times takes no time. Work
    that goes back to an earlier step (a fix during the review) counts in the section that is running then."""
    found: list[datetime | None] = []
    for _title, lo, hi in SECTIONS:
        times = []
        for st in steps[lo : hi + 1]:
            if isinstance(st, dict):
                t = _ms(st.get("startedAt")) or _ms(st.get("endedAt"))
                if t:
                    times.append(t)
        found.append(min(times) if times else None)
    # From the back: a section without times starts where the next one does (zero length), and none starts
    # after a later one (a step reported out of order pulls the boundary back). Within [start, end].
    begins = [start] * len(SECTIONS)
    nxt = end
    for i in range(len(SECTIONS) - 1, 0, -1):
        if found[i] is not None:
            nxt = min(nxt, found[i])  # type: ignore[type-var]
        begins[i] = max(nxt, start)
    return [(begins[i], begins[i + 1] if i + 1 < len(begins) else end) for i in range(len(begins))]


def _elapsed_fields(b: dict) -> dict:
    return {
        "wall_s": round(b["wall"]),
        "active_s": round(b["active"]),
        "review_wait_s": round(b["review_idle"]),
        "review_wait_runs": b["review_runs"],
        "pause_s": round(b["pause"]),
        "pauses": [{"from": _iso(t0), "to": _iso(t1), "seconds": round(secs), "reason": why}
                   for t0, t1, secs, why in b["pauses"]],
    }


def metrics_record(state: dict, repo: str, num: int, sessions: list[str], end: datetime,
                   difficulty: str | None, review_rounds: int | None, pause_min: float,
                   risk: str | None = None) -> dict:
    """The record of one run of the issue (schema 1; see the knowledge base's metrics/README.md)."""
    start = _ms(state.get("startedAt"))
    if start is None:
        raise SystemExit("the state file has no startedAt")
    steps = list(state.get("steps") or [])
    steps += [None] * (len(STEP_NAMES) - len(steps))
    end = max(end, start)
    main, subs = session_files(sessions)
    entries = timeline_entries(main, start, end) if main else []

    def elapsed(t0: datetime, t1: datetime) -> dict:
        if not main:  # no transcript: only the wall clock is known
            return {"wall_s": round((t1 - t0).total_seconds()), "active_s": None, "review_wait_s": None,
                    "review_wait_runs": None, "pause_s": None, "pauses": []}
        return _elapsed_fields(breakdown([e for e in entries if t0 <= e[0] <= t1], t0, t1, pause_min))

    total, models = _tokens(count_tokens(main + subs, start, end)) if main else (None, {})
    sections = []
    for (title, lo, hi), (t0, t1) in zip(SECTIONS, section_bounds(steps, start, end)):
        tok, mod = _tokens(count_tokens(main + subs, t0, t1)) if main else (None, {})
        sections.append({
            "title": title, "steps": [lo, hi], "from": _iso(t0), "to": _iso(t1),
            "elapsed": elapsed(t0, t1), "tokens": tok, "models": mod,
        })
    snaps = state.get("fiveHour") or {}

    def snap(k: str) -> dict | None:
        v = snaps.get(k)
        if not isinstance(v, dict) or not isinstance(v.get("percentUsed"), (int, float)):
            return None
        return {"at": _iso(_ms(v.get("at"))), "percent_used": v["percentUsed"]}

    return {
        "schema": METRICS_SCHEMA,
        "stage": "recorded",
        "repo": repo,
        "issue": num,
        "verb": state.get("verb") or None,
        "started_at": _iso(start),
        "ended_at": _iso(end),
        "finished": isinstance(steps[12], dict) and steps[12].get("state") == "done",
        "recorded_at": _iso(datetime.now(local_tz())),
        "sessions": sessions,
        "transcripts": {"main": len(main), "subagents": len(subs)},
        "difficulty": difficulty,
        "review_rounds": review_rounds,
        "risk": risk,
        "elapsed": elapsed(start, end),
        "tokens": total,
        "models": models,
        "sections": sections,
        "steps": [
            {"step": i, "name": name, "state": st.get("state") if isinstance(st, dict) else None,
             "started_at": _iso(_ms(st.get("startedAt"))) if isinstance(st, dict) else None,
             "ended_at": _iso(_ms(st.get("endedAt"))) if isinstance(st, dict) else None}
            for i, (name, st) in enumerate(zip(STEP_NAMES, steps))
        ],
        # Account-wide: every session of the account moves it, so it is context, never this issue's cost.
        "five_hour": {"scope": "account", "start": snap("start"), "end": snap("end")},
    }


def run_marker(state: dict, repo: str, num: int, sessions: list[str]) -> dict:
    """The run's start marker (schema 1, `stage: "started"`): written once the claim holds, at the path the
    run's record will have, so the record replaces it. A marker that is never replaced is an aborted run."""
    start = _ms(state.get("startedAt"))
    if start is None:
        raise SystemExit("the state file has no startedAt")
    return {
        "schema": METRICS_SCHEMA, "stage": "started", "repo": repo, "issue": num,
        "verb": state.get("verb") or None, "started_at": _iso(start), "ended_at": None, "finished": False,
        "recorded_at": _iso(datetime.now(local_tz())), "sessions": sessions,
    }


def _load_run(a) -> tuple[dict, Path, list[str]] | None:
    """The pane's state file, the knowledge base and the sessions — shared by metrics-start and -record."""
    path = state_file(a.repo, a.num)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"no issue pane state file: {path} (the pane's step tool writes it)", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"invalid JSON in {path}: {e}", file=sys.stderr)
        return None
    kdir = Path(cfg()["knowledge_dir"])
    if not kdir.is_dir():
        print(f"no knowledge base at {kdir}: run /hga:init", file=sys.stderr)
        return None
    sessions = list(getattr(a, "session", None) or [])
    if not sessions:
        for sid in (os.environ.get("CLAUDE_CODE_SESSION_ID"), state.get("session")):
            if sid and sid not in sessions:
                sessions.append(sid)
    return state, kdir, sessions


def record_path(kdir: Path, repo: str, num: int, state: dict) -> Path:
    owner, name = split_repo(repo)
    start_utc = _ms(state.get("startedAt"))
    if start_utc is None:
        raise SystemExit("the state file has no startedAt")
    return kdir / "metrics" / owner.lower() / name.lower() / f"{num}-{start_utc.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.json"


def _write_json(out: Path, data: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def cmd_metrics_start(a) -> int:
    loaded = _load_run(a)
    if loaded is None:
        return 4
    state, kdir, sessions = loaded
    out = record_path(kdir, a.repo, a.num, state)
    try:
        existing = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = None
    if isinstance(existing, dict) and existing.get("stage") != "started":
        print("note: the run's record already exists; the marker does not replace it", file=sys.stderr)
    else:
        _write_json(out, run_marker(state, a.repo, a.num, sessions))
    print(out)
    return 0


def cmd_metrics_record(a) -> int:
    loaded = _load_run(a)
    if loaded is None:
        return 4
    state, kdir, sessions = loaded
    steps = state.get("steps") or []
    report = steps[12] if len(steps) > 12 and isinstance(steps[12], dict) else {}
    end = parse_ts(a.until) if a.until else _ms(report.get("endedAt")) or datetime.now(local_tz())
    rec = metrics_record(state, a.repo, a.num, sessions, end, a.difficulty, a.review_rounds, a.pause_min, a.risk)
    if not rec["transcripts"]["main"]:
        print(f"warning: no transcript for {', '.join(sessions) or 'this session'}: only wall-clock times",
              file=sys.stderr)
    out = record_path(kdir, a.repo, a.num, state)
    _write_json(out, rec)
    print(out)
    return 0


# --- metrics aggregate ---------------------------------------------------------------------------

# Anthropic API list prices, USD per million tokens: (input, output, cache write, cache read). Matched by the
# longest prefix of the model id. Cache writes at the 5-minute rate (1.25 × input; a 1-hour write costs 2 ×), and
# Haiku 5.5 at its rate for prompts up to 100K tokens. An estimate of what the tokens would cost on the API —
# not what a Claude subscription costs.
API_PRICES_AS_OF = "2026-10-06"
API_PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 12.5, 0.25),
    "claude-mythos-5-1": (10.0, 50.0, 12.5, 0.25),
    "claude-fable-5": (10.0, 50.0, 12.5, 1.0),
    "claude-mythos-5": (10.0, 50.0, 12.5, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.2),
    "claude-opus-5": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-8": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-7": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-6": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-5": (5.0, 25.0, 6.25, 0.5),
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.2),
    "claude-sonnet-5": (2.0, 10.0, 2.5, 0.2),
    "claude-sonnet-4": (3.0, 15.0, 3.75, 0.3),
    "claude-haiku-5-5": (0.1, 0.5, 0.125, 0.01),
    "claude-haiku-4-5": (1.0, 5.0, 1.25, 0.1),
}
COST_COLUMN = "api_cost_usd_est"
COST_NOTE = (f"{COST_COLUMN}: an estimate at Anthropic API list prices ({API_PRICES_AS_OF}), "
             "not what a Claude subscription costs")
METRICS_COLUMNS = (
    "kind", "run", "repo", "issue", "verb", "date", "started_at", "ended_at", "finished", "outcome", "difficulty",
    "review_rounds", "risk", "na_steps", "section", "section_index", "model",
    "wall_s", "active_s", "review_wait_s", "pause_s",
    "calls", "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
    "total_tokens",
    "five_hour_start_at", "five_hour_start_pct", "five_hour_end_at", "five_hour_end_pct",
)
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def api_price(model: str) -> tuple[float, float, float, float] | None:
    best = max((p for p in API_PRICES if model.startswith(p)), key=len, default=None)
    return API_PRICES[best] if best else None


def api_cost(model: str, tok: dict) -> float | None:
    """The tokens' cost at API list prices in USD, or None for a model without a price."""
    price = api_price(model)
    if price is None:
        return None
    return sum((tok.get(k) or 0) * p for k, p in zip(TOKEN_KEYS, price)) / 1_000_000


def _token_cols(tok: dict | None) -> dict:
    if not isinstance(tok, dict):
        return {"calls": None, **{k: None for k in TOKEN_KEYS}, "total_tokens": None}
    return {"calls": tok.get("calls"), **{k: tok.get(k) for k in TOKEN_KEYS},
            "total_tokens": sum(tok.get(k) or 0 for k in TOKEN_KEYS)}


def _elapsed_cols(el: dict | None) -> dict:
    el = el if isinstance(el, dict) else {}
    return {k: el.get(k) for k in ("wall_s", "active_s", "review_wait_s", "pause_s")}


def _models_cost(models: dict, unpriced: set[str]) -> float | None:
    """The sum over the models that have a price; None if there are no tokens at all."""
    if not models:
        return None
    total = 0.0
    for m, tok in models.items():
        c = api_cost(m, tok)
        if c is None:
            if _token_cols(tok)["total_tokens"]:
                unpriced.add(m)
        else:
            total += c
    return round(total, 6)


def metrics_rows(rec: dict, run: str, cost: bool, unpriced: set[str], outcome: str | None = None) -> list[dict]:
    """A schema-1 record as flat rows: one for the run, one per section, one per section and model."""
    five = rec.get("five_hour") or {}
    start5, end5 = five.get("start") or {}, five.get("end") or {}
    base = {
        "run": run, "repo": rec.get("repo"), "issue": rec.get("issue"), "verb": rec.get("verb"),
        "date": (rec.get("started_at") or "")[:10] or None, "started_at": rec.get("started_at"),
        "ended_at": rec.get("ended_at"), "finished": rec.get("finished"), "outcome": outcome,
        "difficulty": rec.get("difficulty"),
        "review_rounds": rec.get("review_rounds"),
        "risk": rec.get("risk"),
        # None for a marker (no steps); a count for a record, 0 before the state existed
        "na_steps": None if not isinstance(rec.get("steps"), list) else
        sum(1 for st in rec["steps"] if isinstance(st, dict) and st.get("state") == "not_applicable"),
    }
    empty = {k: None for k in METRICS_COLUMNS}
    rows = [{**empty, **base, "kind": "run", **_elapsed_cols(rec.get("elapsed")), **_token_cols(rec.get("tokens")),
             "five_hour_start_at": start5.get("at"), "five_hour_start_pct": start5.get("percent_used"),
             "five_hour_end_at": end5.get("at"), "five_hour_end_pct": end5.get("percent_used")}]
    if cost:
        rows[0][COST_COLUMN] = _models_cost(rec.get("models") or {}, unpriced)
    for i, sec in enumerate(rec.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        row = {**empty, **base, "kind": "section", "section": sec.get("title"), "section_index": i,
               **_elapsed_cols(sec.get("elapsed")), **_token_cols(sec.get("tokens"))}
        if cost:
            row[COST_COLUMN] = _models_cost(sec.get("models") or {}, unpriced)
        rows.append(row)
        for model, tok in sorted((sec.get("models") or {}).items()):
            mrow = {**empty, **base, "kind": "model", "section": sec.get("title"), "section_index": i,
                    "model": model, **_token_cols(tok)}
            if cost:
                c = api_cost(model, tok)
                mrow[COST_COLUMN] = round(c, 6) if c is not None else None
            rows.append(mrow)
    return rows


def _day(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"not a date (YYYY-MM-DD): {s}")


OUTCOMES = ("finished", "unfinished", "aborted", "open")
STALE_HOURS = 24


def run_outcome(rec: dict, now: datetime, stale_hours: float) -> str | None:
    """`finished` / `unfinished` (a record, step 12 done or not), `aborted` (only the start marker, older than
    stale_hours), `open` (only the marker, still young: the run may be going on). None for a record from before
    the markers (no `stage`): it never had a marker, so it does not count in the abort rate."""
    stage = rec.get("stage")
    if stage == "started":
        try:
            start = parse_ts(rec.get("started_at") or "")
        except ValueError:
            return "aborted"
        return "aborted" if now - start >= timedelta(hours=stale_hours) else "open"
    if stage is None:
        return None
    return "finished" if rec.get("finished") is True else "unfinished"


def outcome_summary(rows: list[dict], stale_hours: float) -> str | None:
    """One line over the run rows' outcomes, with the abort rate: aborted / (finished + unfinished + aborted)."""
    n = Counter(r["outcome"] for r in rows if r["kind"] == "run" and r["outcome"])
    if not n:
        return None
    closed = n["finished"] + n["unfinished"] + n["aborted"]
    rate = f"abort rate {100 * n['aborted'] / closed:.0f}% of {closed}" if closed else "abort rate n/a"
    parts = [f"{n[k]} {k}" for k in OUTCOMES if n[k]]
    return (f"runs with a start marker: {', '.join(parts)} · {rate} (aborted = no record {stale_hours:g} h after "
            "the start; open = younger, not counted)")


def collect_metrics(kdir: Path, repo: str | None, since: str | None, until: str | None,
                    cost: bool, now: datetime | None = None,
                    stale_hours: float = STALE_HOURS) -> tuple[list[dict], list[str]]:
    """The rows of every schema-1 record under <kdir>/metrics/ that matches the filters, and the warnings.
    A start marker replaced by its run's record is gone; one whose run wrote its record under another start
    (same issue, a shared session) is dropped too, so a run counts once."""
    now = now or datetime.now(timezone.utc)
    rows: list[dict] = []
    warnings: list[str] = []
    unknown: Counter = Counter()
    unpriced: set[str] = set()
    root = kdir / "metrics"
    found: list[tuple[Path, dict]] = []
    for path in sorted(root.rglob("*.json")) if root.is_dir() else []:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            warnings.append(f"skipped {path.relative_to(root)}: {e}")
            continue
        schema = rec.get("schema") if isinstance(rec, dict) else None
        if isinstance(schema, bool) or schema != METRICS_SCHEMA:
            unknown[json.dumps(schema)] += 1
            continue
        if repo and str(rec.get("repo") or "").lower() != repo.lower():
            continue
        day = (rec.get("started_at") or "")[:10]
        if (since and day < since) or (until and day > until):
            continue
        found.append((path, rec))

    def ident(r: dict) -> tuple[str, object]:
        return str(r.get("repo") or "").lower(), r.get("issue")

    recorded: dict[tuple[str, object], set[str]] = defaultdict(set)
    for _path, rec in found:
        if rec.get("stage") != "started":
            recorded[ident(rec)].update(x for x in rec.get("sessions") or [] if isinstance(x, str))
    for path, rec in found:
        if rec.get("stage") == "started" and recorded[ident(rec)] & set(rec.get("sessions") or []):
            continue
        rows += metrics_rows(rec, path.relative_to(root).with_suffix("").as_posix(), cost, unpriced,
                             run_outcome(rec, now, stale_hours))
    for schema, n in sorted(unknown.items()):
        warnings.append(f"skipped {n} record(s) with an unknown schema ({schema})")
    if unpriced:
        warnings.append(f"no API price for {', '.join(sorted(unpriced))}: their tokens are not in {COST_COLUMN}")
    order = {"run": 0, "section": 1, "model": 2}
    rows.sort(key=lambda r: (r["started_at"] or "", r["run"], order[r["kind"]], r["section_index"] or 0,
                             r["model"] or ""))
    return rows, warnings


def cmd_metrics(a) -> int:
    kdir = Path(cfg()["knowledge_dir"])
    if not kdir.is_dir():
        print(f"no knowledge base at {kdir}: run /hga:init", file=sys.stderr)
        return 4
    since = _day(a.since) if a.since else None
    until = _day(a.until) if a.until else None
    rows, warnings = collect_metrics(kdir, a.repo, since, until, a.cost, stale_hours=a.stale_hours)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    summary = outcome_summary(rows, a.stale_hours)
    if summary:
        print(f"note: {summary}", file=sys.stderr)
    if a.cost:
        print(f"note: {COST_NOTE}", file=sys.stderr)
    columns = list(METRICS_COLUMNS) + ([COST_COLUMN] if a.cost else [])
    if a.format == "csv":
        w = csv.DictWriter(sys.stdout, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("true" if r[k] else "false") if isinstance(r[k], bool) else r[k] for k in columns})
    else:
        lines = [json.dumps({k: r[k] for k in columns}, ensure_ascii=False) for r in rows]
        print("[\n" + ",\n".join(lines) + "\n]" if lines else "[]")
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


def triage_labels_to_drop(status: str, labels: set[str]) -> list[str]:
    """When work starts, the triage verdict has done its job: the issue should not look ready and in progress."""
    return sorted(labels & set(TRIAGE_LABELS)) if status == "in_progress" else []


def drop_triage_labels(repo: str, num: int, status: str) -> None:
    drop = triage_labels_to_drop(status, label_names(issue_items(repo, num)))
    if drop:
        args = ["issue", "edit", str(num), "--repo", repo]
        for x in drop:
            args += ["--remove-label", x]
        gh(*args)
        print(f"triage label removed: {', '.join(drop)}")


def cmd_status_set(a) -> int:
    status = canonical_status(a.status)
    project = project_name(a)
    drop_triage_labels(a.repo, a.num, status)
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


# --- claim check: before the claim, and the read-back after it -----------------------------------

# The claim comment's machine-read first words (whatever the configured language), and its session tag.
CLAIM_RE = re.compile(r"^\s*Claimed\s*·", re.I)
SESSION_TAG_RE = re.compile(r"·\s*session\s+([0-9A-Za-z_-]{4,})", re.I)
CLAIM_RECENT_H = 24  # a claim comment this recent counts as taken in the check before the claim
CLAIM_MARGIN_S = 60  # the read-back window starts this much before the check (clock skew)
CLAIM_SETTLE_S = 3  # the read-back waits this long, so a parallel claim posted just now is listed
VERIFY_VERBS = ("verify", "re-verify")
EXIT_TAKEN = 5


def session_tag(sid: str | None = None) -> str | None:
    """This session's tag in the claim line: the session id's first 8 characters."""
    sid = sid if sid is not None else os.environ.get("CLAUDE_CODE_SESSION_ID")
    return sid[:8] if sid else None


def parse_claims(comments: list[dict]) -> list[dict]:
    """The issue's claim comments, oldest first (GitHub's time, then its comment id for the same second).
    A withdrawn claim is edited to start with "Withdrawn", so it is no longer listed."""
    out = []
    for c in comments:
        body = c.get("body") or ""
        if not CLAIM_RE.match(body):
            continue
        tag = SESSION_TAG_RE.search(body.splitlines()[0])
        out.append({"id": c.get("id"), "at": parse_ts(c["created_at"]), "author": c.get("user") or "?",
                    "url": c.get("url") or "", "session": tag.group(1)[:8] if tag else None})
    return sorted(out, key=lambda c: (c["at"], c["id"] or 0))


def status_key(status: str | None) -> str | None:
    """The workflow key (todo / in_progress / done) of a board or label status, by the configured names."""
    if not status:
        return None
    s = status.strip().lower()
    return {v.lower(): k for k, v in cfg()["github"]["statuses"].items()}.get(s) or CANONICAL.get(s)


def _claim_line(c: dict) -> str:
    who = c["author"] + (f", session {c['session']}" if c["session"] else "")
    return f"{_iso(c['at'])} by {who}: {c['url']}"


def claim_check(*, status: str | None, assignees: list[str], me: str | None, claims: list[dict],
                tag: str | None, now: datetime, verb: str | None = None,
                since: datetime | None = None) -> tuple[int, list[str]]:
    """The verdict and its lines. Without `since`: the check before the claim — taken if the issue is In
    Progress (Done too, unless the verb verifies), assigned to another account, or claimed by another session
    in the last 24 hours. With `since` (the read-back after the claim): the earliest claim posted since then
    wins; a later one withdraws."""
    if since is not None:
        window = [c for c in claims if c["at"] >= since]
        mine = next((c for c in window if tag and c["session"] == tag), None)
        if mine is None:
            return 4, [f"Verdict: no claim of this session (session {tag}) since {_iso(since)} — post it first"]
        lines = [f"Your claim: {mine['url']} (comment id {mine['id']})"]
        key = (mine["at"], mine["id"] or 0)
        earlier = [c for c in window if not (tag and c["session"] == tag) and (c["at"], c["id"] or 0) < key]
        if earlier:
            first = earlier[0]
            return EXIT_TAKEN, lines + [f"Earlier claim: {_claim_line(first)}",
                                        f"Verdict: later — withdraw your claim and stop ({first['author']} was first)"]
        return 0, lines + ["Verdict: first — the issue is yours"]
    own = [c for c in claims if tag and c["session"] == tag]
    if own:
        # A resumed run: its claim holds only if no other session's claim within a day before it stands — the
        # run may have died between its claim and the read-back, while the other session won.
        mine = own[0]
        key = (mine["at"], mine["id"] or 0)
        lines = [f"Your claim: {mine['url']} (comment id {mine['id']})"]
        earlier = [c for c in claims if c["session"] != tag and (c["at"], c["id"] or 0) < key
                   and mine["at"] - c["at"] <= timedelta(hours=CLAIM_RECENT_H)]
        if earlier:
            first = earlier[0]
            return EXIT_TAKEN, lines + [f"Earlier claim: {_claim_line(first)}",
                                        f"Verdict: later — withdraw your claim and stop ({first['author']} was first)"]
        return 0, lines + ["Verdict: yours — this session claimed it first; continue"]
    reasons = []
    state = status_key(status)
    if state == "in_progress":
        reasons.append(f"Status {status}")
    elif state == "done" and (verb or "").lower() not in VERIFY_VERBS:
        reasons.append(f"Status {status} (implemented, waiting for the merge; only verify / re-verify take it)")
    other_accounts = [x for x in assignees if not me or x.lower() != me.lower()]
    if other_accounts:
        reasons.append(f"assigned to {', '.join(other_accounts)}")
    others = [c for c in claims if not (tag and c["session"] == tag)]
    recent = [c for c in others if now - c["at"] <= timedelta(hours=CLAIM_RECENT_H)]
    if recent:
        reasons.append(f"claimed by {recent[-1]['author']} at {_iso(recent[-1]['at'])}")
    lines = [f"Status: {status or 'unknown'} · assignees: {', '.join(assignees) or 'none'} · claims: {len(claims)}"]
    lines += [f"  claim {_claim_line(c)}" for c in claims[-5:]]
    lines.append(f"Session: {tag or 'unknown (no CLAUDE_CODE_SESSION_ID)'}")
    start = now - timedelta(seconds=CLAIM_MARGIN_S)
    lines.append(f"Read back from: {start.timestamp():.0f} ({_iso(start)})")
    if reasons:
        return EXIT_TAKEN, lines + [f"Verdict: taken — {'; '.join(reasons)}"]
    return 0, lines + ["Verdict: free — claim it, then read it back"]


def workflow_status(issue: dict, project: str | None) -> str | None:
    """The status the workflow keeps: the board's Status field (None if not on the board), or the labels."""
    if not project:
        return label_status(label_names(issue))
    for n in issue["projectItems"]["nodes"]:
        if n["project"]["title"] == project:
            return (n.get("fieldValueByName") or {}).get("name")
    return None


def cmd_claim_check(a) -> int:
    since = None
    if a.since:
        since = (datetime.fromtimestamp(float(a.since), local_tz()) if re.fullmatch(r"\d+(\.\d+)?", a.since)
                 else parse_ts(a.since))
        time.sleep(CLAIM_SETTLE_S)
    owner, name = split_repo(a.repo)
    issue = issue_items(a.repo, a.num)
    assignees = json.loads(gh("api", f"repos/{owner}/{name}/issues/{a.num}", "--jq", "[.assignees[].login]"))
    raw = gh("api", "--paginate", f"repos/{owner}/{name}/issues/{a.num}/comments", "--jq",
             ".[] | {id, created_at, body, user: .user.login, url: .html_url}")
    comments = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
    me = gh("api", "user", "--jq", ".login").strip() or None
    code, lines = claim_check(
        status=workflow_status(issue, project_name(a)), assignees=assignees, me=me, claims=parse_claims(comments),
        tag=session_tag(), now=datetime.now(local_tz()), verb=a.verb, since=since,
    )
    print(f"{a.repo}#{a.num}: {issue['title']} · issue: {issue['state']}")
    print("\n".join(lines))
    return code


# --- risk class: which gates a change needs ----------------------------------------------------

RISK_CLASSES = ("low", "standard", "high")
# The gates each class changes (the issue skill's gate matrix), printed with the class as its evidence.
RISK_GATES = {
    "low": [
        "4 Decisions: not_applicable if nothing was decided",
        "5 Build + tests: the gate runs; new test cases not_applicable",
        "6 Live test: not_applicable (no runtime change)",
        "8 Review: one local round at low level, no bot",
        "11 Knowledge: not_applicable if nothing new was learned",
    ],
    "standard": ["every step as the skill describes it"],
    "high": [
        "4 Decisions: the maintainer's decision is required",
        "5 Build + tests: the new tests must fail on the base",
        "6 Live test: required; only the maintainer can waive it",
        "7 PR: at least one manual review point, and a rollback note",
        "8 Review: local at high level, and the bot if one is configured",
    ],
}


def glob_re(pattern: str) -> re.Pattern:
    """A file pattern as a regex: `**/` any folders (or none), `**` anything, `*` and `?` within one name."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def path_matches(path: str, pattern: str) -> bool:
    """Without "/" the pattern matches the file name anywhere; with "/", the path from the repository root."""
    target = path if "/" in pattern else path.rsplit("/", 1)[-1]
    return bool(glob_re(pattern.lstrip("/")).match(target))


def risk_patterns(repo: str) -> tuple[list[str], list[str], str]:
    """(low, high, high label) for the repository: its own low patterns replace the team's, its high ones add."""
    risk = cfg()["risk"]
    over = next((v for k, v in (risk.get("repos") or {}).items() if k.lower() == repo.lower()), None) or {}
    low = list(over["low_paths"]) if "low_paths" in over else list(risk["low_paths"])
    high = list(risk["high_paths"]) + [p for p in over.get("high_paths") or [] if p not in risk["high_paths"]]
    return low, high, risk["high_label"]


def classify_risk(files: list[str], low: list[str], high: list[str], labels: set[str],
                  high_label: str) -> tuple[str, list[dict], list[str]]:
    """The class, each file's match ({file, kind: high | low | other, pattern}) and the reasons."""
    rows, reasons = [], []
    for f in files:
        h = next((p for p in high if path_matches(f, p)), None)
        lo = None if h else next((p for p in low if path_matches(f, p)), None)
        rows.append({"file": f, "kind": "high" if h else "low" if lo else "other", "pattern": h or lo})
    if any(lab.lower() == high_label.lower() for lab in labels):
        reasons.append(f"label {high_label}")
    hits = [r for r in rows if r["kind"] == "high"]
    if hits:
        reasons.append(f"{len(hits)} file(s) match a high pattern")
    if reasons:
        return "high", rows, reasons
    if rows and all(r["kind"] == "low" for r in rows):
        return "low", rows, ["every file matches a low pattern"]
    other = [r["file"] for r in rows if r["kind"] == "other"]
    return "standard", rows, [f"{len(other)} file(s) match no low pattern"]


def worktree_files(wt: str, base: str | None) -> list[str]:
    def run(*args: str) -> str:
        res = subprocess.run(["git", "-C", wt, *args], capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:2])}…: {res.stderr.strip()[:300]}")
        return res.stdout

    if not base:
        head = subprocess.run(["git", "-C", wt, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
                              capture_output=True, text=True, encoding="utf-8")
        base = head.stdout.strip() or "origin/main"
    mb = run("merge-base", base, "HEAD").strip()
    # The working tree against the merge base: committed, staged and unstaged changes; both names of a rename
    changed = run("diff", "--name-only", "--no-renames", mb).splitlines()
    untracked = run("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({f for f in changed + untracked if f})


def cmd_risk(a) -> int:
    if bool(a.worktree) == bool(a.pr):
        raise SystemExit("risk: give either --worktree <dir> or --pr <n>")
    owner, name = split_repo(a.repo)
    labels: set[str] = set()
    if a.pr:
        raw = gh("api", "--paginate", f"repos/{owner}/{name}/pulls/{a.pr}/files", "--jq",
                 ".[] | .filename, (.previous_filename // empty)")
        files = sorted({f for f in raw.splitlines() if f})
        labels |= set(json.loads(gh("pr", "view", str(a.pr), "--repo", a.repo, "--json", "labels",
                                    "--jq", "[.labels[].name]")))
        source = f"PR #{a.pr}"
    else:
        files = worktree_files(a.worktree, a.base)
        source = f"worktree {a.worktree} since its merge base with {a.base or 'the default branch'}"
    if a.issue:
        labels |= set(json.loads(gh("issue", "view", str(a.issue), "--repo", a.repo, "--json", "labels",
                                    "--jq", "[.labels[].name]")))
    low, high, high_label = risk_patterns(a.repo)
    cls, rows, reasons = classify_risk(files, low, high, labels, high_label)
    if a.json:
        print(json.dumps({"repo": a.repo, "risk": cls, "reasons": reasons, "source": source, "files": rows,
                          "gates": RISK_GATES[cls]}, ensure_ascii=False))
    else:
        print(f"Risk: {cls} · {'; '.join(reasons)} · {len(files)} file(s), {source}")
        for r in rows:
            print(f"  {r['kind']:<5} {r['file']}" + (f"  ({r['pattern']})" if r["pattern"] else ""))
        print("Gates: " + " · ".join(RISK_GATES[cls]))
    if not files:
        print("no changed file: nothing to classify", file=sys.stderr)
        return 4
    return 0


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
    """The provider's bot: a Bot account (not a person whose name happens to contain the provider's)."""
    user = c.get("user") or {}
    return user.get("type") == "Bot" and bool(PROVIDERS[provider]["login"].search(user.get("login") or ""))


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


# A dismissed review is no result; a pending one is not submitted yet.
COUNTED_REVIEW_STATES = {"APPROVED", "COMMENTED", "CHANGES_REQUESTED"}


def head_reviews(reviews: list[dict], head: str) -> list[dict]:
    """The submitted reviews of the head commit (`head` is the full SHA, or the prefix --sha gave)."""
    return [r for r in reviews
            if r.get("state") in COUNTED_REVIEW_STATES and (r.get("commit_id") or "").startswith(head)]


def wait_review(a, provider: str, head: str) -> tuple[int | None, dict | None]:
    deadline = time.monotonic() + a.timeout_min * 60
    while time.monotonic() < deadline:
        done = head_reviews(bot_reviews(a.repo, a.pr, provider), head)
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
    comments = review = None
    changes_requested = False
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
        # Requested changes without inline comments are findings in the review's body, not a clean result
        changes_requested = review.get("state") == "CHANGES_REQUESTED"
        clean_result = not inline and not changes_requested
    if comments is None:
        comments = json.loads(gh("api", f"repos/{a.repo}/issues/{a.pr}/comments", "--paginate"))
    rounds = count_rounds(provider, bot_reviews(a.repo, a.pr, provider), comments)
    if clean_result:
        print(f"Round: {rounds} · Result: no significant findings (👍)")
        return 0
    if changes_requested and not inline:
        print(f"Round: {rounds} · Result: changes requested in the review's body, no inline findings"
              f" · {review.get('html_url') or ''}")
        for ln in (review.get("body") or "").strip().splitlines()[:20]:
            print(f"  {ln}")
    else:
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
  blockedBy(first:50){nodes{number title state stateReason}}
  blocking(first:50){nodes{number title state stateReason}}}}}
"""


def is_done(issue: dict) -> bool:
    """Closed = GitHub's CLOSED state, whatever the reason (completed, not planned, duplicate)."""
    return issue.get("state") == "CLOSED"


def state_text(issue: dict) -> str:
    """`closed · NOT_PLANNED`: the reason matters to a dependent, which may need vetting again."""
    if not is_done(issue):
        return "open"
    return f"closed · {issue['stateReason']}" if issue.get("stateReason") else "closed"


NEXT_Q = """
query($o:String!,$n:String!,$after:String,$field:String!){repository(owner:$o,name:$n){
  issues(states:OPEN,first:100,after:$after,orderBy:{field:CREATED_AT,direction:ASC}){
    pageInfo{hasNextPage endCursor}
    nodes{number title labels(first:20){nodes{name}} blockedBy(first:20){nodes{number state}}
      assignees(first:10){nodes{login}}
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
            print(f"    #{x['number']} [{state_text(x)}] {x['title']}")
    open_blockers = [x["number"] for x in issue["blockedBy"]["nodes"] if not is_done(x)]
    unplanned = [x["number"] for x in issue["blockedBy"]["nodes"] if x.get("stateReason") in ("NOT_PLANNED", "DUPLICATE")]
    if unplanned:
        print(f"  CLOSED WITHOUT COMPLETION: {', '.join(f'#{n}' for n in unplanned)} — check that this issue still holds")
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
    buckets: dict[str, list[dict]] = {k: [] for k in BUCKET_TITLES}
    off_board = 0
    for i in issues:
        labels = label_names(i)
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
        assignees = [x["login"] for x in ((i.get("assignees") or {}).get("nodes") or [])]
        buckets[key].append({"number": i["number"], "title": i["title"], "blockers": blockers, "assignees": assignees})
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
            + (f"  [assigned: {', '.join(r['assignees'])}]" if r["assignees"] else "")
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
    p.add_argument("--until")
    p.add_argument("--session", action="append")
    p = sub.add_parser("metrics-record")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("--difficulty", choices=DIFFICULTIES)
    p.add_argument("--review-rounds", type=int)
    p.add_argument("--risk", choices=RISK_CLASSES, help="the class `HGA risk` gave (its last run)")
    p.add_argument("--until")
    p.add_argument("--session", action="append")
    p.add_argument("--pause-min", type=float, default=15)
    p = sub.add_parser("metrics", help="the knowledge base's metrics records as flat rows (one per run, section, "
                                       "section and model)")
    p.add_argument("--repo", help="owner/repo")
    p.add_argument("--since", help="first start date, YYYY-MM-DD")
    p.add_argument("--until", help="last start date, YYYY-MM-DD (inclusive)")
    p.add_argument("--format", choices=("json", "csv"), default="json")
    p.add_argument("--cost", action="store_true", help=f"add {COST_COLUMN}: an estimate at API list prices, "
                                                        "not a subscription cost")
    p.add_argument("--stale-hours", type=float, default=STALE_HOURS,
                   help="a start marker without its record this long after the start is an aborted run")
    p = sub.add_parser("metrics-start")
    p.add_argument("repo")
    p.add_argument("num", type=int)
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
    p = sub.add_parser("claim-check")
    p.add_argument("repo")
    p.add_argument("num", type=int)
    p.add_argument("--verb", help="the claim verb: verify / re-verify may take an issue that is Done")
    p.add_argument("--since", help="the read-back after the claim: the check's `Read back from` value")
    p.add_argument("--project")
    p = sub.add_parser("risk")
    p.add_argument("repo")
    p.add_argument("--worktree", help="the worktree whose changes are classified")
    p.add_argument("--base", help="the base ref of --worktree (default: origin's default branch)")
    p.add_argument("--pr", type=int, help="the PR whose files are classified")
    p.add_argument("--issue", type=int, help="the issue, for its labels (risk.high_label)")
    p.add_argument("--json", action="store_true")
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
            for problem in config_problems(cfg()):
                print(f"warning: configuration: {problem}", file=sys.stderr)
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
            "metrics-start": cmd_metrics_start,
            "metrics-record": cmd_metrics_record,
            "metrics": cmd_metrics,
            "status": cmd_status,
            "status-set": cmd_status_set,
            "track": cmd_track,
            "meta": cmd_meta,
            "review-request": cmd_review_request,
            "review-wait": cmd_review_wait,
            "claim-check": cmd_claim_check,
            "risk": cmd_risk,
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
