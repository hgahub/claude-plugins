---
name: triage
description: Use when a GitHub issue is to be vetted, prepared for implementation, picked next, or handed to a parallel /hga:issue session — the step before /hga:issue. Branches — the five questions ("vet issue #N", "run the five questions"), finalizing the issue into an implementable brief ("finalize #N", "make it ready for implementation"), choosing the next issue ("which issue next?", "when can #N start?", or no issue given), and launching the implementation session. Works for any GitHub repository.
user-invocable: true
argument-hint: "[issue URL | owner/repo#number] — empty: the next issue, in continuous mode"
---

# Triage

Prepares an issue **before** implementation (`hga:issue`), and hands the finished issue to a parallel
implementation session. The request decides which branch runs:

| Branch | Request | Writes to GitHub? |
|---|---|---|
| A. Vet — the five questions | "vet issue #N", "run the five questions" | no; writes to the knowledge base |
| B. Finalize | "finalize #N", "make it ready for implementation" | yes: body, prerequisite edges, state label |
| C. Next issue | "which issue next?", "when can #N start?", **a call without an issue** | no |
| D. Launch | "launch #N", or automatically after B in continuous mode | no; starts a new session |

**Continuous mode** (a call without an issue, or "bring the next one"): C → A → B → D → C … Your decision
points are branch B's questions; the launch is automatic. Outside continuous mode, B ends with a question
instead (B.9). It stops when there is no issue to vet, when the
5-hour plan usage is above `parallel.usage_ceiling_pct` (`mcp__ccd_session_mgmt__get_usage`, where available),
or when you stop it.

## Common frame

- **Preparation, not implementation.** No claim, the status stays Todo, no code is committed. The claim and
  every later step belong to the launched `hga:issue` session.
- **Settings:** `HGA config` once at the start — `language` (everything written to GitHub and the knowledge
  base), `github.project` (board or labels), `slack`, `parallel.max_per_repo`, `parallel.usage_ceiling_pct`,
  `labels.closed`, `knowledge_dir`.
- **One triage session per repository, in that repository's main checkout** (`HGA repo-check`): the launched
  implementation starts in the triage session's folder.
- **Today's default branch is the measure.** Read the code in a detached scratch worktree
  (`git worktree add --detach <scratchpad>/wt<n> origin/<default-branch>`); do not touch the main checkout's
  branch. Every claim gets the short SHA next to it.
- **Measure on the real modules,** with fictitious or sample data; only read databases. The app's pitfalls and
  test data are on the knowledge base's `workflow/<app>.md` page.
- **Closing belongs to the maintainer.** If the issue is already implemented or unnecessary, propose closing it.
- **What closing is:** the PR merged, the status Done, and the maintainer added the closing label
  (`labels.closed`, default `done`). That is enough: an issue with the closing label is closed, and its dependents'
  prerequisite is met. "Close issue" (the `CLOSED` state) is **not** this — a later, independent event; do not
  wait for it and do not ask for it. `HGA deps` / `next` count accordingly (closing label or `CLOSED` → closed).
- **Outgoing calls with finished text, in a separate call.** Write the body with the `Write` tool to the
  scratchpad, and send it with `--body-file`.
- **Helper script:** `HGA` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/issue/scripts/hga_issue.py"` (on Windows
  `python`) — `config`, `repo-check`, `status`, `track`, `deps`, `block`, `triage-state`, `meta`, `next`,
  `midnight`. Write it out in full in every Bash call, or define a shell function first —
  `hga() { python3 "${CLAUDE_PLUGIN_ROOT}/skills/issue/scripts/hga_issue.py" "$@"; }` — a shell variable does
  not work (zsh does not split it into words).
- **Dashboard (the hga plugin's triage panel).** If the session has the `mcp__hga__phase` tool, call it **at
  every branch change** (`branch`: A / B / C / D, `issue`: `owner/repo#n`, `step`: what you are doing now, in one
  short line), at **every verdict** of branch A (`verdicts`: `current` 2, `complete` 3, `feasible` 4, `problem`
  5, `preceded` 6 — `yes` / `partly` / `no`), at the proposed or applied state (`proposed`), and when the number
  of open decisions waiting for the user changes (`decisions`). Give only the changed fields. The panel is a live
  view; write your answer regardless. If the tool is missing, skip it — not an error.

## States

The triage result is a label on the issue (the board's Status, or the status labels, stay Todo / In Progress /
Done):

| Label | Meaning |
|---|---|
| `ready-for-agent` | Implementable, no decision needed: `hga:issue` can take it |
| `ready-for-human` | Needs a maintainer decision or manual work (name which) |
| `needs-info` | Information is missing (name what, and from whom) |

A prerequisite is a native "blocked by" edge (`HGA block`), not text: branch C and `hga:issue` work from it.

## A. Vet — the five questions

1. **Preparation.**
   - `HGA repo-check <owner/repo>`,
     `gh issue view <n> --repo <owner/repo> --json title,body,state,labels,assignees,updatedAt,comments` (not
     `--comments`: outside a terminal it prints only the comments, never the body), `HGA status …`, `HGA deps …`.
   - `git fetch origin`; the worktree on the default branch.
   - Knowledge base (`hga:knowledge`): the app's page, its map, and the issue's earlier notes (search `notes/`
     for the issue number), with their dates.
2. **Still current?**
   - **Is it implemented already?** Search for the behavior by its concept (function, data field, rule), and
     say where you searched.
   - What changed in the affected code since the issue was last updated
     (`git log --since=<updatedAt> -- <files>`), and which open PR touches the same code.
3. **Is the issue complete?** *Every* producer and consumer of the mechanism (search for the function, the
   field); contradictions with other issues, decisions, knowledge base notes; open maintainer decisions.
4. **Is it feasible?** **Reproduce** the bug or the gap on the real modules. The result: *confirmed* (with the
   code path), *not reproducible*, or *not enough information*. Estimate the size: affected modules, whether a
   test harness exists.
5. **Which problem does it solve?** The effect a user can see. Mark measured and inferred claims separately
   ("inference").
6. **Is it preceded by another open issue?** Open issues and PRs that touch the same function, data format or
   rule. Which must close first, and why: these become branch B's prerequisite edges.
7. **Knowledge base:** a note at `notes/<app>-<n>-<short-name>.md` (date, SHA, the measurement's steps), map,
   validation, commit and push as the `hga:knowledge` skill says. Then remove the worktree.
8. **Answer:** five headings with the questions, each starting with a bold verdict (**Yes** / **Partly** /
   **No**), then the evidence. At the end:
   - **Proposed state:** one of the three labels, with one sentence of reasoning;
   - **Proposed prerequisite:** `#m` and why, or "none".

**Done** when all five questions are answered with evidence (SHA, measurement, function name), the note is
validated, and the worktree is gone.

## B. Finalize

1. If branch A has not run for this issue in this session, run it first.
2. **Decisions:** ask the open questions with `AskUserQuestion` (the recommended option first,
   "(Recommended)"), and record the answers with the date. A decision skill (e.g. TypeSafe) only on request.
3. **The body** is the implementer's contract (GitHub's edit history keeps the old one). `Write` it to the
   scratchpad, in this structure:
   ```
   **Ref:** <origin: issue / PR / review round> · related: #… (why)
   ## Goal                     one or two sentences: what must be true after the issue
   ## Current behavior         the mechanism, with function and type names
   ## What we measured         date, default-branch SHA, environment, steps, result
   ## Decisions                the maintainer's decisions, with dates
   ## Implementation           behavior and key interfaces: what it returns, stores, prints
   ## Acceptance criteria      numbered, each checkable on its own; including the regression
                               test that fails on the base, and the live check
   ## Not part of it           the boundaries and the follow-up issues
   ## Prerequisite             #m (why), if any
   ```
   "Implementation" describes behavior and interfaces, with function and type names. File:line goes stale
   quickly; if needed, it goes under "What we measured", tied to the SHA.
4. **Write and read back:** `gh issue edit <n> --repo <owner/repo> --body-file <file>`, then
   `gh issue view <n> --repo <owner/repo> --json body`: the body matches the file.
5. **Prerequisites:** `HGA block <owner/repo> <n> --by <m>[,<m>…]`. Each appears as a prerequisite in the output.
6. **State:** `HGA triage-state <owner/repo> <n> <label>`, and `HGA status …`: Todo (with a board, if the issue
   is not on it: `HGA track`).
7. **Knowledge base:** the finalization in the note (decisions, SHA, state, prerequisite), validation.
8. **Report:** the issue's link, the decisions, the body's sections one line each, the state label and the
   prerequisites.
9. With `ready-for-agent`: in continuous mode, or if the request asked for a launch, branch D follows without
   asking. Otherwise ask (`AskUserQuestion`): "Launch a parallel implementation now (Recommended)", "Not now" —
   the user may want to implement it in this session, or only prepare issues.

**Done** when the body, the edges and the label are read back, the note is validated, and (outside continuous
mode) the user answered the launch question.

## C. Next issue

1. **Cleanup:** delete the launchers that are finished (branch D, point 7).
2. `HGA next <owner/repo>`: ready, needs a human, blocked (with prerequisites), needs info, untriaged, in
   progress, in review.
3. Today's claims: with Slack, `HGA midnight` → `slack_read_channel` `oldest` on `slack.channel_id`; without it,
   the assignees of the ready issues. An issue already claimed drops out.
4. **Proposal:** among the ready issues, the one that does not collide with running implementations and open PRs
   (same function, file, data format), with the reasoning. If none is ready, the untriaged one where branch A
   brings the most (oldest, largest impact). In continuous mode the proposed issue goes on to branch D if it is
   ready, or to branch A if it is untriaged, without asking.
5. **"When can #N start?":** `HGA deps <owner/repo> <n>` — the open prerequisites, each with its state (Todo /
   In Progress / open PR).

**Done** when the proposal names the issue, its open prerequisites, and the result of the collision check.

## D. Launch — a parallel implementation session

A `ready-for-agent` issue is taken end to end by a new session, visible in the sidebar, with `hga:issue`. The
launcher is a manual (unscheduled) scheduled task with the id `hga-issue-<repo>-<n>`; the session starts in the
triage session's folder, in auto permission mode.

1. **Conditions** — all must hold, otherwise the issue waits, and the report says for what:
   - the label is `ready-for-agent`, and `HGA deps` shows no open prerequisite;
   - **at most `parallel.max_per_repo` running implementations per repository** (default 2): the
     `list_scheduled_tasks` tasks starting with `hga-issue-<repo>-` that have a `running` run according to
     `list_task_runs`;
   - it does not collide with any running implementation's issue (same function, file, data format — from the
     issues' "Implementation" sections and the open PRs' files). On a collision,
     `HGA block <owner/repo> <n> --by <running issue>`, and the issue starts after it;
   - the 5-hour plan usage is below `parallel.usage_ceiling_pct`.
2. **Issue metadata — before the launcher, read back:**
   - First read what is already set: `HGA meta <owner/repo> <n>`. Fields shown as `n/a` do not exist for this
     owner or board: skip them.
   - **Type**, from the issue body and branch A: `Bug` (a measured deviation from the expected behavior),
     `Feature` (a new function or capability), `Task` (everything else: refactoring, docs, infrastructure,
     measurement) — only if the owner has issue types.
   - **Priority**: `Urgent` (blocks work or production, no workaround), `High` (blocks another issue, or a bug
     users can see), `Medium` (the default), `Low` (cosmetic, can wait).
   - **Effort**, from the "Implementation" section's extent: `Low` (one module, at most half a day), `Medium`
     (several files or layers, about a day), `High` (several layers or data formats, a migration, more than a
     day).
   - **Fill in only empty fields.** Do not overwrite what the maintainer set; if you would propose something
     else, say so in the report.
   - **Iteration:** with a board that has an iteration field, always the current one. If the issue was on
     another one, say so in the report.
   - Setting: `HGA meta <owner/repo> <n> [--type <T>] [--priority <P>] [--effort <E>] [--iteration current]`.
     The output line is the evidence (`Type: … · Priority: … · Effort: … · Iteration: …`); on a non-zero exit the
     issue does not start, and the report says what did not take effect.
   - **Labels:** you do not set them. From the repo's existing labels (`gh label list --repo <owner/repo>`) —
     and a new one if justified — you propose, apart from the state labels (`ready-for-*`, `needs-info`) and the
     closing label. In the report: "Label proposal: `x`, `y` (new: `z`)" — the maintainer adds and sets them.
3. **Launcher**, if the session has the scheduled-tasks tools (Claude Desktop):
   `mcp__scheduled-tasks__create_scheduled_task`, without a schedule:
   - `taskId`: `hga-issue-<repo>-<n>`, `title`: `hga:issue <repo>#<n>`, `notifyOnCompletion`: true;
   - `prompt` (self-contained, because the session does not see this conversation): "Load the `hga:issue` skill
     with the Skill tool, and take this issue end to end: <issue URL>. The issue is finalized with `hga:triage`
     (`ready-for-agent`); the body's "Implementation" and "Acceptance criteria" sections are the contract. The
     merge is the maintainer's: stop after the report, and wait for their message."

   **Without those tools** (CLI, web), launch nothing: give the user the same prompt in a code block, and the
   command to start it in the repository's main checkout (`claude "<prompt>"`), then continue with branch C.
4. **Start:** `mcp__scheduled-tasks__run_scheduled_task`, then `mcp__ccd_session_mgmt__get_session` on the
   returned id, where available: it runs, and its `cwd` is the repository's checkout.
5. **Report:** the issue and the session's link (`[hga:issue <repo>#<n>](#<session_id>)`), the `HGA meta` line,
   and if any, the label proposal and the differing field proposals. Then back to branch C.
6. **Feedback:** at the end of the run (after `hga:issue`'s report) the triage session gets a notification; the
   slot is free, the next ready issue can go. The maintainer writes about the merge directly to the
   implementation session.
7. **Cleanup (branch C, point 1):** deleting a launcher also archives its session, so delete it
   (`delete_scheduled_task`) only when the issue is Done, the PR is `MERGED`, and the session has finished the
   post-merge steps too (according to `list_events`).

**Done** when the session runs in the repository's checkout and the report gave its link — or the report named
the condition the issue is waiting for, or (without the tools) the user has the prompt.
