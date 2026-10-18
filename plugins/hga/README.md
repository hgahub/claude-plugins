# hga — from GitHub issue to reviewed pull request

One Claude Code plugin with seven skills, three live panes and a progress band. An issue's path:
**`/hga:intent`** turns a few sentences into an intent.md in the knowledge base, by interviewing and research,
**`/hga:new-issue`** makes an issue from it, **`/hga:triage`** prepares it, **`/hga:issue`** takes it to a
reviewed PR, **`/hga:knowledge`** keeps what was learned on the way, **`/hga:dashboard`** shows how the runs
went, and **`/hga:init`** sets everything up.

```
/hga:intent → /hga:new-issue → /hga:triage → /hga:issue
```

| | What it does |
|---|---|
| `/hga:init [new \| join <URL> \| check]` | Checks the prerequisites, creates or joins the knowledge base (a private GitHub repository, another git host, or local only), writes the machine and team configuration and a short usage guide in the team's language (`workflow/hga-guide.md`, optionally a Docs copy), and on a re-run repairs what the check found |
| `/hga:intent [intent]` | Interviews (1–3 questions per round) and researches (knowledge base, the default branch, issues, docs) until the picture is complete; an intent.md under `notes/`, with a readiness gate (`intent_check.py`: PASS / WARN / BLOCK) and the author's approval; then the issue and the triage |
| `/hga:new-issue <intent>` | An issue from the intent: readiness gate, duplicate search, the body from the intent's sections, create and read back, board (Todo) and type, the issue number back into the intent |
| `/hga:triage [issue]` | Vets an issue (five questions), finalizes it for implementation, picks the next one, launches a parallel implementation session |
| `/hga:issue <issue>` | Claim (Slack or GitHub, read back: the earliest claim wins) → In Progress → worktree → build and test, live test in the browser (with a tester's verdict and fix rounds) → PR → review → Done → cleanup → knowledge base → report, on a verified checklist |
| `/hga:knowledge [question]` | Reads and writes the knowledge base, with dates and sources |
| `/hga:dashboard [refresh]` | A claude.ai Dashboard over the metrics records: lead time, elapsed per section, tokens and an API-price cost estimate per section and model, review rounds, the account's five-hour usage — filterable by repository and period; creates it on first use, refreshes it afterwards |
| `/issue-pane` | Toggles the issue pane (the running issue's 13 steps) |
| `/triage-pane [refresh \| owner/repo]` | Toggles the triage dashboard |
| `/intent-pane` | Toggles the intent pane (the band above the prompt comes by itself) |

> The panes are built on Claude Code's mod API (early access, it may change from release to release). Written
> and tested with Claude Code 2.1.289. The skills work without the panes.

## Install

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Then run `/hga:init` once per machine. Update with `claude plugin update hga@hga-plugins`, then
`/reload-plugins` (or a new session).

**Prerequisites** — without them the skills stop, they do not break anything:

- `gh` logged in, with the `repo` scope (and `project` if you use a GitHub project board), and write access to
  the repositories you work on.
- Python 3.9+ (the scripts use only the standard library; on Windows, a named time zone needs `pip install
  tzdata`). `uv` for live tests of Python apps (optional).
- Optional: a Slack MCP connector (claims and reports in a channel), Claude in Chrome or the built-in browser of
  the desktop app (live tests), a review bot on your repositories (Codex, Copilot or Greptile).

`/hga:init check` (or `python3 <plugin>/skills/issue/scripts/hga_issue.py doctor`) shows what is missing; the
check also offers to repair it — a moved knowledge base, an invalid configuration field, a leftover
`labels.closed`, template files a newer plugin version added.

## Configuration

Two layers, merged (`hga_issue.py config` prints the result):

- **Team** — `hga.config.json` in the knowledge base, versioned and shared:

  ```json
  {
    "language": "en",
    "timezone": null,
    "github": {
      "project": null,
      "fields": { "status": "Status", "iteration": "Iteration", "priority": "Priority", "effort": "Effort" },
      "statuses": { "todo": "Todo", "in_progress": "In Progress", "done": "Done" }
    },
    "labels": { "in_progress": "in-progress", "in_review": "in-review" },
    "slack": null,
    "review": { "provider": "local", "ask_after_rounds": 5 },
    "parallel": { "max_per_repo": 2, "usage_ceiling_pct": 80 },
    "risk": {
      "low_paths": ["*.md", "*.mdx", "*.rst", "*.txt", "docs/**", "LICENSE", "LICENSE.*", "tests/**", "test/**"],
      "high_paths": ["**/migrations/**", "*.sql", "**/auth/**", "**/permissions/**", ".github/workflows/**"],
      "high_label": "risk:high",
      "repos": {}
    }
  }
  ```

- **Machine** — `~/.claude/hga/config.json`: `knowledge_dir` (default `~/.hga/knowledge`), `guide_doc_url` (the
  user's Docs copy of the guide, if any), `dashboard_url` (the user's metrics dashboard, written by
  `/hga:dashboard`), and any team field to override on this machine.

| Key | Meaning |
|---|---|
| `language` | Language of everything written outward: commits, PRs, issues, comments, Slack, notes. Code follows the repository's own conventions. |
| `timezone` | `null` = the machine's; an IANA name makes "today" (Slack claims, iterations) the same for the whole team. |
| `github.project` | `null` = no board: the status is kept with labels. Otherwise the project's title; its status field and option names map through `fields.status` and `statuses`. Iteration, Priority and Effort are used only if they exist. |
| `labels` | Without a board: `in_progress` while an agent works, `in_review` after step 9 (implemented, waiting for the maintainer). There is no closing label: issues close with GitHub's own closing — the PR's `Closes #n` at merge, or `gh issue close`. |
| `slack` | `null` = claims and reports are GitHub comments on the issue. Otherwise `{"channel": "#dev", "channel_id": "C…"}`. |
| `review.provider` | `local` (the `code-review` skill), `codex`, `copilot` or `greptile` (a bot on GitHub, in addition to the local review). `ask_after_rounds`: from this round on, the maintainer decides whether to close the review. |
| `parallel` | `/hga:triage` launches at most `max_per_repo` implementations per repository, and none above `usage_ceiling_pct` of the 5-hour plan usage. |
| `risk` | The risk classes of `hga_issue.py risk`: `high` if a changed file matches `high_paths` or the issue / PR has `high_label`; `low` if every file matches `low_paths`; `standard` otherwise. A pattern without `/` matches the file name anywhere; with `/`, the path from the repository root (`**` spans folders). A team's list replaces the default one. Per repository, `repos.<owner/repo>.low_paths` replaces the team's list and `high_paths` adds to it — e.g. a repository whose `*.md` files are runtime prompts sets its own `low_paths`. The class decides which steps of `/hga:issue` may be `not_applicable`. |

`hga_issue.py config` prints a malformed field as a warning on stderr (the JSON still comes out); `doctor` counts
it as a missing item.

## The knowledge base

A file-based collection of notes about your applications and environments, usually a private git repository
shared by the team. Every claim carries a date and a source, so it is treated as evidence, not as truth. The
skills read it before they work (the app's page, its workflow page, earlier notes about the issue) and write
to it afterwards.

```
~/.hga/knowledge/
  00-index.md        the entry point: what is where
  apps/              one page per application
  environments/      hosts, ports, deployments
  architecture/      what calls what
  notes/             new, dated findings (/hga:issue step 11 writes here): <app>-<issue>-<topic>.md,
                     and the intents of /hga:intent: <app>-intent-<topic>.md
  inbox/             raw input waiting to be processed
  workflow/          /hga:issue's app-specific pages (start, gate, live test, pitfalls)
  quality/           contradictions between sources and measurements
  policies/          source-order.md, the evidence rules
  map/               generated note map per app
  metrics/           one JSON metrics record per /hga:issue run (step 12 writes it)
  hga.config.json    the team configuration
```

- **Reading:** `/hga:knowledge <question>`, or step 0 of `/hga:issue` and `/hga:triage`. The skill pulls first.
- **Writing:** a new finding goes to `notes/` with frontmatter (`title`, `verified_at`, `status`,
  `review_after_days`) and a `## Sources and verification` section. Canonical pages change only with evidence.
  No secrets, passwords, tokens or personal data.
- **After writing:** `kb_commit.py -m "<message>" -- <pages>` takes a lock in the knowledge base's `.git`
  (parallel sessions write the same checkout), snapshots the last commit plus the given pages in a temporary
  index, rebuilds the note map (`build_map.py`) and validates (`validate_kb.py`: frontmatter, links,
  credential-like content) in that snapshot, commits exactly it, then pulls with rebase and pushes — so what is
  validated is what is committed, without other sessions' unfinished pages. The skills do this
  themselves; the scripts are in `skills/knowledge/scripts/`.

### The metrics record

At the end of step 12, `hga_issue.py metrics-record <owner/repo> <n>` writes the run's numbers as JSON to
`metrics/<owner>/<repo>/<n>-<start>.json` in the knowledge base, and the skill commits that one file. One file
per run, so parallel sessions never conflict and a re-run of the issue gets a new file. A record holds:

- the start and end, and each of the 13 steps' start and end (the issue pane stamps them);
- the elapsed breakdown — wall clock, active time, review wait, pauses — for the run and for each section
  (Prepare, Build, Review, Finish);
- tokens from the session transcripts (subagents included), in total, per section and per model;
- the difficulty and the review rounds as reported;
- the account's five-hour usage at the start and the end. This is account-wide (every session moves it), so it
  is context, never the issue's cost.

Once the claim holds (step 1), `hga_issue.py metrics-start <owner/repo> <n>` writes a **run marker** to the same
path (`"stage": "started"`), which the record overwrites at step 12. A marker that is still there a day after
its start is a run that never reached the report: the aggregate reports it as `aborted`, and the dashboard shows
the abort rate.

The schema (`"schema": 1`) is in the knowledge base's `metrics/README.md`; `validate_kb.py` checks each
record. Records are data for aggregation per repository and period; nothing reads them back into a session.

### The dashboard

`hga_issue.py metrics [--repo owner/repo] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--format json|csv] [--cost]`
flattens every schema-1 record (others are skipped with a warning) into rows for charts: `kind=run` (one per
run), `kind=section` (one per run and section) and `kind=model` (one per run, section and model). Sections add
up to their run, models to their section. `--cost` adds `api_cost_usd_est`: the tokens at Anthropic API list
prices from a small table in the script — an estimate of what they would cost on the API, **not** what a Claude
subscription costs.

`/hga:dashboard` uploads those rows (CSV) to a claude.ai **Dashboard** artifact as an attached file: tiles,
lead time per issue by difficulty, solving speed per week, elapsed by section (stacked), tokens and the cost
estimate by section and model, review rounds, and the account's five-hour usage as context; filters for the
repository and the period. The knowledge base stays local, so the dashboard is a snapshot:
`/hga:dashboard refresh` uploads new rows. Its link is kept as `dashboard_url` in the machine configuration.
Whoever can open the dashboard can read the attached rows; it is private until you share it.

## Review providers

| Provider | How it is asked | Waiting |
|---|---|---|
| `local` | The `code-review` skill on the PR, repeated after each round of fixes | — |
| `codex` | `@codex review` comment (the Codex GitHub app must be installed) | `review-wait` reads the Codex summary comment and its inline findings |
| `copilot` | `gh pr edit --add-reviewer @copilot` (Copilot code review must be enabled; gh 2.88+) | `review-wait` waits for Copilot's review of the head commit |
| `greptile` | `@greptileai` comment (the Greptile GitHub app must be installed) | `review-wait` waits for Greptile's review of the head commit |

The local review runs on every PR, whatever the provider. Copilot and Greptile support is newer than Codex's:
report problems as issues.

## The panes

### Issue pane

`/hga:issue`'s 13 steps (0 Start … 12 Report) in four sections (Prepare, Build, Review, Finish). At the top the
issue, the counter and the elapsed time, below it a progress bar per section; each section is one row
(`5/5 ›`, `1/2 · 1 skipped ›`), and only the running section is open, with its steps and evidence. Clicking a
section's name opens or closes it.

![The issue pane mid-run: four sections, the running Review section open with its evidence](docs/issue-panel.png)

- Steps: ✓ done (green) · ◐ in progress · ! skipped, with the reason · ○ not yet. Section icons: ☰ Prepare,
  ✎ Build, ⌕ Review, ⚑ Finish. One accent color (the running step and the bar), green checks and a warning
  color — everything else dim; colors are theme keys.
- The model reports the state with the `mcp__hga__step` tool (`issue`, `step` 0–12, `state`, `evidence`,
  `verb`, `started_at`, `checks`); `/hga:issue`'s checklist section requires a call at every state change.
- A long evidence ends in `…` on a narrow pane: **double-click** the step's name to wrap the row onto several
  lines, double-click again to bring it back to one.
- **Manual review** (☑, under the Review section): with the PR, the model lists at most 13 points (`checks`) that
  only a person can check; the reviewer ticks them by clicking ☐. The tick goes into the state file, and a point
  with the same text keeps its tick when a new list arrives; an empty list reads "no highlighted manual review
  point". The section stays open while a point is unticked, and the step tool's answer gives the standing too
  (`Manual review: 2/5 ticked.`).
- A button on the right of the footer (`🎫 web-app#142 8/13`, dim while the pane is closed) toggles the pane;
  so does `/issue-pane`. The first report opens the pane; once you close it, only a new issue reopens it.

  ![The footer button: the issue and its progress](docs/footer-button.png)

- Every report writes its state to `~/.claude/hga/issue/<owner>-<repo>-<n>.json`: from there the triage panel
  sees the implementations running in parallel. The file also keeps each step's start and end and the
  five-hour usage at step 0's start and step 12's `done`: the metrics record is made from them. After a plugin update or restart the pane restores the session's
  own issue from that file.

### Triage panel

In the same style: the running implementations of the repository (with a slot counter against
`parallel.max_per_repo`), the finished ones, the current triage branch with the five verdicts, and the issue
groups of `hga_issue.py next` (Ready, Needs a human, Blocked, Needs info, In progress, In review, Untriaged).

![The triage panel: branch B with the five verdicts, one running implementation, the issue groups](docs/triage-panel.png)

- **Launch:** the implementation starts as a **subtask** of the triage session (`start_session`,
  `use_worktree: true`, without `cwd` — the main checkout is the same project, so the app would drop a `cwd`;
  the work happens in a `../<repo>-<n>` worktree opened from the main checkout): it shows nested under the
  triage in the sidebar, the triage gets a
  notification when it ends a turn, and archives it after the merge. Archiving the triage archives its subtasks
  too. (Before 0.2.0 a manual scheduled task, `hga-issue-<repo>-<n>`, launched it.)
- **Activation:** loading `/hga:triage` (or the Skill tool), `/triage-pane`, a `next` run, or a `phase` call. The
  repository comes from the session's git remote; `/triage-pane owner/repo` switches.
- **Running:** from the issue pane's state files, every minute. An unfinished issue silent for 60 minutes is
  marked stalled and frees its slot; past Done (step 9) it no longer takes a slot. Finished issues stay for a day,
  unfinished ones for a week; ✕ hides one until it reports again. In the desktop app, an issue's name jumps to
  its session.
- **Issues:** `hga_issue.py next <repo> --json` every five minutes, and right away after a session changes a
  label, a prerequisite or a status.
- **Why `-pane`:** `/issue` and `/triage` are taken by the plugin's own skills (`/hga:issue`'s short name is
  `/issue`). If a pane command cannot be registered, the mod says so in a toast; the panes still work from the
  footer button and the skills.

### Intent pane and progress band

Shows `/hga:intent`'s run, in the same color scheme as the other two panes.

- **Pane** (`/intent-pane`): at the top the intent's name and the issue, below it the **full picture** bar — the
  coverage of the intent.md's eight sections (✓ done = 1, ◐ partial = ½, ○ empty), the number of open questions
  and the readiness gate's verdict (PASS green, WARN yellow, BLOCK red). Then the nine stations (Intent, Context,
  Interview, Research, Draft, Approval, Knowledge base, Issue, Handoff) with their evidence, and the sections one
  by one.
- **Progress band above the prompt:** the whole path in one row —
  `◎ web-app-intent-xlsx-source  ◐ Intent 6/8 · 1 question · WARN › ○ Issue › ○ Triage › ○ Build  ✕`.
  Issue turns green with the issue number, Triage shows its branch if it runs in the same session
  (`mcp__hga__phase`), and Build shows the counter and the clock from the issue's state file
  (`~/.claude/hga/issue/`), whichever session it runs in. Clicking the intent's name opens the pane, `✕` hides
  the band (a new intent shows it again); during a survey the band gives way.
- The model reports with the `mcp__hga__intent` tool (`intent`, `step` 0–8 + `state`, `evidence`, `sections`,
  `questions`, `verdict`, `file`, `issue`); only the changed fields are needed.
- Every report writes the state to `~/.claude/hga/intent/<intent>.json`. After a plugin update or restart, at
  start and on `/intent-pane`, the intent comes back from there — only the session's own (by the `session`
  field). If the write fails, the pane works the same.

### The readiness gate

`skills/intent/scripts/intent_check.py <intent.md> [--json]` — without a model: from 100 points, −45 per error
and −20 per warning; BLOCK if there is an error, PASS from 85. Errors: a missing title; an empty problem, desired
outcome or affected section; no numbered criterion; no "Given … when … then …" scenario; a `[blocking]` open
question; a leftover placeholder (`<…>`, TBD, TODO). Warnings: no edge case, fewer scenarios than criteria, a
current state without a SHA, an empty "Out of scope". The `##` headings and the scenario keywords are fixed
English markers, whatever the configured language. Self-test: `--self-test`.

## Development

```
claude --plugin-dir ./plugins/hga     # load it; this also generates the types
claude plugin validate plugins/hga
claude plugin test plugins/hga
python3 -m pytest plugins/hga/tests/py
```

Only one hooks module can be loaded per plugin, so `hooks/register.tsx` calls the three panes' `register`. An
event without a matcher can be bound only once: the panes' `ui.close` filter on `id`, and the triage panel's
`session.start` uses a `{ cwd: /(?:)/ }` matcher, the intent pane's `{ cwd: /^/ }`, both matching every session. `isInteractive` is not a usable
filter: the desktop app runs in SDK mode, where it is false.
