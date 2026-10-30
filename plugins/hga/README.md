# hga — from GitHub issue to reviewed pull request

One Claude Code plugin with seven skills, three live panes and a progress band. An issue's path:
**[`/hga:intent`](skills/intent/SKILL.md)** turns a few sentences into an intent.md in the knowledge base, by interviewing and research,
**[`/hga:new-issue`](skills/new-issue/SKILL.md)** makes an issue from it, **[`/hga:triage`](skills/triage/SKILL.md)** prepares it, **[`/hga:issue`](skills/issue/SKILL.md)** takes it to a
reviewed PR, **[`/hga:knowledge`](skills/knowledge/SKILL.md)** keeps what was learned on the way, **[`/hga:dashboard`](skills/dashboard/SKILL.md)** shows how the runs
went, and **[`/hga:init`](skills/init/SKILL.md)** sets everything up.

```
/hga:intent → /hga:new-issue → /hga:triage → /hga:issue
```

The groups below describe each skill's primary role. All seven skills can be invoked by either the user or
Claude; the grouping does not restrict invocation.

### User-invoked

Entry points for setting up the plugin, starting work and inspecting results. Triage can also launch
[`/hga:issue`](skills/issue/SKILL.md) in an implementation session.

| Command | What it does |
|---|---|
| [`/hga:init [quick \| new \| join <URL> \| check]`](skills/init/SKILL.md) | `quick`: a local setup with the defaults and at most two questions; otherwise checks the prerequisites, creates or joins the knowledge base (a private GitHub repository, another git host, or local only), writes the machine and team configuration and a short usage guide in the team's language (`workflow/hga-guide.md`, optionally a Docs copy), and on a re-run repairs what the check found |
| [`/hga:intent [intent]`](skills/intent/SKILL.md) | Interviews (1–3 questions per round) and researches (knowledge base, the default branch, issues, docs) until the picture is complete; an intent.md under `notes/`, with a readiness gate (`intent_check.py`: PASS / WARN / BLOCK) and the author's approval; then the issue and the triage |
| [`/hga:triage [issue]`](skills/triage/SKILL.md) | Vets an issue (five questions), finalizes it for implementation, picks the next one, launches a parallel implementation session |
| [`/hga:issue <issue>`](skills/issue/SKILL.md) | Claim (Slack or GitHub, read back: the earliest claim wins) → In Progress → worktree → build and test, live test in the browser (with a tester's verdict and fix rounds) → PR → review → In review → cleanup → knowledge base → report, on a verified checklist |
| [`/hga:dashboard [refresh]`](skills/dashboard/SKILL.md) | A claude.ai Dashboard over the metrics records: lead time, elapsed per section, tokens and an API-price cost estimate per section and model, review rounds, the account's five-hour usage — filterable by repository and period; creates it on first use, refreshes it afterwards |

### Model-invoked

Helpers Claude can use within a workflow: [`/hga:intent`](skills/intent/SKILL.md) calls
[`/hga:new-issue`](skills/new-issue/SKILL.md) after approval, and
[`/hga:knowledge`](skills/knowledge/SKILL.md) supplies context and records verified findings.
You can also invoke either command directly.

| Command | What it does |
|---|---|
| [`/hga:new-issue <intent>`](skills/new-issue/SKILL.md) | An issue from the intent: readiness gate, duplicate search, the body from the intent's sections, create and read back, board (Todo) and type, the issue number back into the intent |
| [`/hga:knowledge [question]`](skills/knowledge/SKILL.md) | Reads and writes the knowledge base, with dates and sources |

### Panes

Commands that toggle live views of the workflows. The progress band above the prompt appears automatically
while an intent is running.

| Command | What it does |
|---|---|
| [`/issue-pane`](#issue-pane) | Toggles the issue pane (the running issue's 13 steps) |
| [`/triage-pane [refresh \| owner/repo]`](#triage-panel) | Toggles the triage dashboard |
| [`/intent-pane`](#intent-pane-and-progress-band) | Toggles the intent pane (the band above the prompt comes by itself) |

> The panes are built on Claude Code's mod API (early access, it may change from release to release). Written
> and tested with Claude Code 2.1.289. The skills work without the panes.

## Install

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Then run [`/hga:init quick`](skills/init/SKILL.md) once per machine: a local knowledge base with the defaults
(status labels, GitHub's own closing, GitHub comments instead of Slack, local review), after at most two
questions. `/hga:init` changes any of it later and offers the choices `quick` skipped; to join a team's knowledge
base, run `/hga:init join <git URL>` instead. Update with `claude plugin update hga@hga-plugins`, then
`/reload-plugins` (or a new session).

**Prerequisites** — without them the skills stop, they do not break anything:

- `gh` logged in, with the `repo` scope (and `project` if you use a GitHub project board), and write access to
  the repositories you work on.
- Python 3.9+ (the scripts use only the standard library; on Windows, a named time zone needs `pip install
  tzdata`). `uv` for live tests of Python apps (optional).
- The `code-review` skill, which comes with Claude Code: every PR's review runs it, also with a review bot.
  `/hga:init` and `/hga:issue` check for it; if it is missing, `claude update` and start a new session.
- Optional: a Slack MCP connector (claims and reports in a channel), Claude in Chrome or the built-in browser of
  the desktop app (live tests), a review bot on your repositories (Codex, Copilot or Greptile).

[`/hga:init check`](skills/init/SKILL.md) (or `python3 <plugin>/skills/issue/scripts/hga_issue.py doctor [--repo owner/repo]`) shows what is missing — with a board, also a status name it has no option for; the
check also offers to repair it, and asks the choices the team configuration lacks (deferred by `quick` or an
older version) — a moved knowledge base, an invalid configuration field, a leftover
`labels.closed` (moved to `labels.closing` or removed), template files a newer plugin version added.

## Configuration

Two layers, merged (`hga_issue.py config` prints the result; `config --repo <owner/repo>` a repository's view):

- **Team** — `hga.config.json` in the knowledge base, versioned and shared:

  ```json
  {
    "language": "en",
    "timezone": null,
    "github": {
      "project": null,
      "fields": { "status": "Status", "iteration": "Iteration", "priority": "Priority", "effort": "Effort" },
      "statuses": { "todo": "Todo", "in_progress": "In Progress", "in_review": "In Review", "done": "Done" }
    },
    "labels": { "in_progress": "in-progress", "in_review": "in-review", "closing": null },
    "slack": null,
    "review": { "provider": "local", "ask_after_rounds": 5 },
    "parallel": { "max_per_repo": 2, "usage_ceiling_pct": 80 },
    "live_test": { "browser": "builtin" },
    "risk": {
      "low_paths": ["*.md", "*.mdx", "*.rst", "*.txt", "docs/**", "LICENSE", "LICENSE.*", "tests/**", "test/**"],
      "high_paths": ["**/migrations/**", "*.sql", "**/auth/**", "**/permissions/**", ".github/workflows/**"],
      "high_label": "risk:high",
      "repos": {}
    },
    "size": { "small": { "files": 3, "lines": 60 }, "large": { "files": 15, "lines": 500 } },
    "repos": {}
  }
  ```

- **Machine** — `~/.claude/hga/config.json`: `knowledge_dir` (default `~/.hga/knowledge`), `guide_doc_url` (the
  user's Docs copy of the guide, if any), `dashboard_url` (the user's metrics dashboard, written by
  [`/hga:dashboard`](skills/dashboard/SKILL.md)), and any team field to override on this machine.

| Key | Meaning |
|---|---|
| `language` | Language of everything written outward: commits, PRs, issues, comments, Slack, notes. Code follows the repository's own conventions. |
| `timezone` | `null` = the machine's; an IANA name makes "today" (Slack claims, iterations) the same for the whole team. |
| `github.project` | `null` = no board: the status is kept with labels. Otherwise the project's title; its status field and option names map through `fields.status` and `statuses`: `in_review` is set by step 9 (implemented, waiting for the maintainer), `done` after the merge — map both to the same option to keep one status for both. `doctor` reports a status name the board has no option for. Turn on the board's built-in "Item closed" workflow (→ Done) so a merge that closes the issue moves it even without the agent. Iteration, Priority and Effort are used only if they exist. |
| `labels` | Without a board: `in_progress` while an agent works, `in_review` after step 9 (implemented, waiting for the maintainer) until the issue closes — there is no Done label. `closing`: `null` (default) = issues close with GitHub's own closing — the PR's `Closes #n` at merge, or `gh issue close`; a label name (e.g. `done`) = the maintainer closes an issue with that label after the merge: the PR says only `Ref #n`, the issue may stay open, the label counts as closed for prerequisites and in triage, and the agent never adds it. |
| `repos` | Per repository (`owner/repo`, any case): its own `github` and `labels`, merged field by field over the team's, for every command that names the repository — e.g. `{"acme/tools": {"github": {"project": null}, "labels": {"closing": null}}}` for one that has no board and closes with `Closes #n` while the team's other repositories use a board and a closing label. `hga_issue.py config --repo <owner/repo>` prints that repository's view; the skills read it from there. |
| `slack` | `null` = claims and reports are GitHub comments on the issue. Otherwise `{"channel": "#dev", "channel_id": "C…"}`. |
| `review.provider` | `local` (the `code-review` skill), `codex`, `copilot` or `greptile` (a bot on GitHub, in addition to the local review). `ask_after_rounds`: from this round on, the maintainer decides whether to close the review. |
| `live_test.browser` | `builtin` (the desktop app's browser) or `chrome` (Claude in Chrome): which one [`/hga:issue`](skills/issue/SKILL.md)'s live test tries first; the other one is the fallback. |
| `parallel` | [`/hga:triage`](skills/triage/SKILL.md) launches at most `max_per_repo` implementations per repository, and none above `usage_ceiling_pct` of the 5-hour plan usage. |
| `risk` | The risk classes of `hga_issue.py risk`: `high` if a changed file matches `high_paths` or the issue / PR has `high_label`; `low` if every file matches `low_paths`; `standard` otherwise. A pattern without `/` matches the file name anywhere; with `/`, the path from the repository root (`**` spans folders). A team's list replaces the default one. Per repository, `repos.<owner/repo>.low_paths` replaces the team's list and `high_paths` adds to it — e.g. a repository whose `*.md` files are runtime prompts sets its own `low_paths`. The class decides which steps of [`/hga:issue`](skills/issue/SKILL.md) may be `not_applicable`. |
| `size` | The size class `hga_issue.py risk` prints next to the risk class, counted over the changed files that match no low pattern (tests and docs do not count): `small` up to `small.files` files and `small.lines` changed lines, `large` above `large.files` or `large.lines`, `medium` between. A `standard` change of size `small` takes the **quick track** of [`/hga:issue`](skills/issue/SKILL.md): one local review round at `medium`, no bot round (`hga_issue.py evidence --step 8` does not require one), and steps 4 and 11 may be `not_applicable`; the regression test, the gate and the live test stay. The size also goes into the report and the metrics record, next to the issue's Effort, so the limits can be calibrated against the measured runs. |

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

- **Reading:** [`/hga:knowledge <question>`](skills/knowledge/SKILL.md), or step 0 of [`/hga:issue`](skills/issue/SKILL.md) and [`/hga:triage`](skills/triage/SKILL.md). The skill pulls first.
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
- the difficulty and the review rounds as reported, the risk and size classes, and the issue's Effort;
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

[`/hga:dashboard`](skills/dashboard/SKILL.md) uploads those rows (CSV) to a claude.ai **Dashboard** artifact as an attached file: tiles,
lead time per issue by difficulty (without pauses by default — `lead_s` = `wall_s` − `pause_s`, so a machine
that was off overnight does not count; a filter puts the pauses back), solving speed per week, elapsed by section (stacked), tokens and the cost
estimate by section and model, review rounds, and the account's five-hour usage as context; filters for the
repository and the period. The knowledge base stays local, so the dashboard is a snapshot:
[`/hga:dashboard refresh`](skills/dashboard/SKILL.md) uploads new rows. Its link is kept as `dashboard_url` in the machine configuration.
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

[`/hga:issue`](skills/issue/SKILL.md)'s 13 steps (0 Start … 12 Report) in four sections (Prepare, Build, Review, Finish). At the top the
issue, the counter and the elapsed time, below it a progress bar per section; each section is one row
(`5/5 ›`, `1/2 · 1 skipped ›`), and only the running section is open, with its steps and evidence. Clicking a
section's name opens or closes it.

![The issue pane mid-run: four sections, the running Review section open with its evidence](docs/issue-panel.png)

- Steps: ✓ done (green) · ◐ in progress · ! skipped, with the reason · ○ not yet. Section icons: ☰ Prepare,
  ✎ Build, ⌕ Review, ⚑ Finish. One accent color (the running step and the bar), green checks and a warning
  color — everything else dim; colors are theme keys.
- The model reports the state with the `mcp__hga__step` tool (`issue`, `step` 0–12, `state`, `evidence`,
  `verb`, `started_at`, `checks`); [`/hga:issue`](skills/issue/SKILL.md)'s checklist section requires a call at every state change.
- **Machine-checked steps** — 3 Worktree, 5 Build + tests, 7 PR, 8 Review, 9 In review: their ✓ means a script
  checked the facts, not only that the model typed evidence. `HGA evidence <owner/repo> <n> --step N` checks them
  (the worktree and its base; the gate's exit code on the current HEAD and files, recorded by `HGA gate`; the
  PR's state, head and closing reference (or `Ref #n` where the skill uses it); an unchanged head, finished CI
  and, with a review bot (not for a low class or the quick track), a clean review of the head recorded by
  `review-wait` or the maintainer's closing with its follow-up issue; the status read back) and writes
  `~/.claude/hga/issue/<owner>-<repo>-<n>.evidence.json`. The step tool rejects such a step's `done` when the
  record is missing, a fact failed, the entry was edited, or it is older than the step's `in_progress`.
  Still reported by the model, not checked: the local `code-review` result, test counts and base failures, the
  live test, and the other steps.
- A long evidence ends in `…` on a narrow pane: **double-click** the step's name to wrap the row onto several
  lines, double-click again to bring it back to one.
- **Manual review** (☑, under the Review section): with the PR, the model lists at most 13 points (`checks`) that
  only a person can check — check tasks on the finished change along the review criteria (scope, correctness,
  security, compatibility, …), not decisions that belonged before the build; the reviewer ticks them by clicking ☐. The tick goes into the state file, and a point
  with the same text keeps its tick when a new list arrives; an empty list reads "no highlighted manual review
  point". The section stays open while a point is unticked, and the step tool's answer gives the standing too
  (`Manual review: 2/5 ticked.`).
- A button on the right of the footer (`🎫 web-app#142 8/13`, dim while the pane is closed) toggles the pane;
  so does [`/issue-pane`](#issue-pane). The first report opens the pane; once you close it, only a new issue reopens it.

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
- **Activation:** loading [`/hga:triage`](skills/triage/SKILL.md) (or the Skill tool), [`/triage-pane`](#triage-panel), a `next` run, or a `phase` call. The
  repository comes from the session's git remote; [`/triage-pane owner/repo`](#triage-panel) switches.
- **Running:** from the issue pane's state files, every minute. An unfinished issue silent for 60 minutes is
  marked stalled and frees its slot; past In review (step 9) it no longer takes a slot. Finished issues stay for a day,
  unfinished ones for a week; ✕ hides one until it reports again. In the desktop app, an issue's name jumps to
  its session.
- **Issues:** `hga_issue.py next <repo> --json` every five minutes, and right away after a session changes a
  label, a prerequisite or a status.
- **Why `-pane`:** `/issue` and `/triage` are taken by the plugin's own skills ([`/hga:issue`](skills/issue/SKILL.md)'s short name is
  `/issue`). If a pane command cannot be registered, the mod says so in a toast; the panes still work from the
  footer button and the skills.

### Intent pane and progress band

Shows [`/hga:intent`](skills/intent/SKILL.md)'s run, in the same color scheme as the other two panes.

- **Pane** ([`/intent-pane`](#intent-pane-and-progress-band)): at the top the intent's name and the issue (a link to GitHub), below it the **full picture** bar — the
  coverage of the intent.md's eight sections (✓ done = 1, ◐ partial = ½, ○ empty), the number of open questions
  and the readiness gate's verdict (PASS green, WARN yellow, BLOCK red). Then the nine stations (Intent, Context,
  Interview, Research, Draft, Approval, Knowledge base, Issue, Handoff) with their evidence, and the sections one
  by one.
- **Progress band above the prompt:** the intent's path in one row —
  `◎ web-app-intent-xlsx-source  ◐ Intent Interview · 1 question · WARN › ○ Issue  ✕`.
  While the intent runs, Intent shows the current station; once the issue exists it turns green with the issue
  number, a link to GitHub. Triage and the build are not on the band: they run in parallel, often several at
  once, and their own panes show them. After the handoff (station 8 done or skipped) the band goes by itself.
  Clicking the intent's name opens the pane, `✕` hides the band (a new intent shows it again); during a survey
  the band gives way.
- The model reports with the `mcp__hga__intent` tool (`intent`, `step` 0–8 + `state`, `evidence`, `sections`,
  `questions`, `verdict`, `file`, `issue`); only the changed fields are needed.
- Every report writes the state to `~/.claude/hga/intent/<intent>.json`. After a plugin update or restart, at
  start and on [`/intent-pane`](#intent-pane-and-progress-band), the intent comes back from there — only the session's own (by the `session`
  field). If the write fails, the pane works the same.

### The readiness gate

`skills/intent/scripts/intent_check.py <intent.md> [--json]` — without a model: from 100 points, −45 per error
and −20 per warning; BLOCK if there is an error, PASS from 85. Errors: a missing title; an empty problem, desired
outcome or affected section; no numbered criterion; no "Given … when … then …" scenario; a `[blocking]` open
question; a leftover placeholder (`<…>`, TBD, TODO). Warnings: no edge case, fewer scenarios than criteria, a
current state without a SHA, an empty "Out of scope". The `##` headings and the scenario keywords are fixed
English markers, whatever the configured language. Self-test: `--self-test`.

## Development

See [CONTRIBUTING.md](../../CONTRIBUTING.md).
