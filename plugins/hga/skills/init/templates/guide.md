<!--
How /hga:init fills this in (this comment does not go into the page):
- Write the page in the team's `language` (hga.config.json): translate every sentence, keep the commands, file
  names and config keys as they are.
- {{…}} are values from `HGA config` and the knowledge base's git remote. A line marked [board] / [no board],
  [closing label] / [github closing], [slack] / [no slack], [bot] / [local] or [remote] / [local only] stays only if it matches the configuration;
  drop the marker itself.
- `{{RISK_…_PATHS}}` lists the patterns in backticks; `{{RISK_REPO_OVERRIDES}}` names the repositories with their
  own `risk.repos` patterns ("own low paths: acme/prompts"), or says "no per-repository overrides".
- `[repos]` lines stay only if `repos` has entries; `{{REPO_OVERRIDES}}` names each repository with what it
  changes ("acme/tools: no board, GitHub's own closing").
- Keep it short: what is here is the whole page. Do not add the plugin's internals; link to them instead.
-->
---
title: "How we use hga"
verified_at: "{{DATE}}"
status: verified
review_after_days: 90
managed_by: hga-init
---

# How we use hga

hga takes a piece of work from an idea to a reviewed pull request, and writes down what was learned on the way.
This page describes **our** setup; `/hga:init` rewrites it whenever the settings change.

## The path of a piece of work

```
idea → /hga:intent → /hga:new-issue → /hga:triage → /hga:issue → reviewed PR → merge
                                                        ↘ /hga:knowledge (along the way)
```

| Step | Command | What happens | What you do |
|---|---|---|---|
| 1. Describe | `/hga:intent` | Claude asks 1–3 questions per round and researches until the picture is complete, then writes an intent into the knowledge base. | Answer the questions, approve the intent. |
| 2. File | `/hga:new-issue` | The intent becomes a GitHub issue, checked for duplicates. | Nothing, unless it finds a duplicate. |
| 3. Prepare | `/hga:triage <owner/repo>` | The issue is assessed with five questions and labeled `ready-for-agent`, `ready-for-human` or `needs-info`; it can start the implementation in a parallel session. | Decide the open questions it lists. |
| 4. Implement | `/hga:issue <issue URL>` | Claim, worktree, code and tests, live test in the browser, PR, review, report — on a 13-step checklist in the issue pane. | Approve what it asks, decide when the review is closed, merge. |
| 5. Remember | `/hga:knowledge` | Answers from the knowledge base, and records verified findings with a date and a source. | Ask; say "write this down" when something is worth keeping. |

## Our settings

| Setting | Value | What it means for you |
|---|---|---|
| Knowledge base | `{{KNOWLEDGE_DIR}}` | Notes, intents and app pages live here. |
| [remote] Shared copy | `{{REMOTE}}` | The team shares it with git; the skills pull before they read and push what they write. |
| [local only] Shared copy | none | Only this machine has it; `/hga:init` can add a remote later. |
| Language | `{{LANGUAGE}}` | Commits, PRs, issues, comments and notes are written in this language. |
| [board] Status | project board "{{PROJECT}}" | Issues move Todo → In Progress → In Review → Done on the board: In Review when Claude has finished and the PR waits for you, Done after the merge. Turn on the board's "Item closed" workflow so a merge moves the issue to Done by itself. |
| [no board] Status | labels `{{LABEL_IN_PROGRESS}}`, `{{LABEL_IN_REVIEW}}` | No board: the status is a label on the issue. |
| [github closing] Closing | GitHub's own | The PR says `Closes #n`: merging it closes the issue. |
| [closing label] Closing | label `{{CLOSING_LABEL}}` | The PR only says `Ref #n`. After the merge, you add `{{CLOSING_LABEL}}` — that closes the issue for us (prerequisites, triage); Claude never adds it. |
| [repos] Exceptions | {{REPO_OVERRIDES}} | These repositories keep their status and closing their own way; the rows above hold for the rest. |
| Live test | {{BROWSER}} first | `/hga:issue` tests the change in this browser, or in the other one if this one is not in the session. |
| [slack] Claims and reports | Slack {{SLACK_CHANNEL}} | Taking an issue is announced there, and the final report goes into that thread. |
| [no slack] Claims and reports | GitHub comments | Taking an issue and the final report are comments on the issue. |
| [local] Review | local `code-review` | Claude reviews its own PR and fixes the findings, round after round. |
| [bot] Review | local `code-review` + {{REVIEW_PROVIDER}} | After the local review, {{REVIEW_PROVIDER}} reviews the PR on GitHub; Claude fixes and answers its findings. |
| Review rounds | {{ASK_AFTER_ROUNDS}} | From this round on, you decide whether to close the review (with a follow-up issue if needed). |
| Parallel work | {{MAX_PER_REPO}} per repository, up to {{USAGE_CEILING_PCT}}% of the 5-hour plan usage | `/hga:triage` starts no more implementations than this. |
| Risk classes | high: {{RISK_HIGH_PATHS}} or the label `{{RISK_HIGH_LABEL}}`; low: {{RISK_LOW_PATHS}} ({{RISK_REPO_OVERRIDES}}) | `/hga:issue` sets the class from the changed files. A low change (docs, tests) skips the live test and the bot review; a small standard change (the quick track: a few files and lines outside docs and tests) gets one local review round and no bot review; a high one needs your decision, a rollback note, and only you can waive its live test. Add the label to raise an issue to high; nothing lowers a class. |

## Where you decide

Claude stops and asks before anything that leaves your machine or cannot be undone:

- posting a message or comment on your behalf ([slack] the claim in {{SLACK_CHANNEL}} only if you gave standing
  permission in `~/.claude/CLAUDE.md`);
- closing the review when the rounds stop paying off;
- closing an issue as not needed or duplicate;
- [closing label] closing an issue after the merge, with the label `{{CLOSING_LABEL}}`;
- merging — always yours.

## Where things are in the knowledge base

| Folder | Holds |
|---|---|
| `apps/` | One page per application: repository, how to build, run and test it. |
| `workflow/` | App-specific rules for `/hga:issue` (gate, live test, pitfalls) — and this guide. |
| `notes/` | Dated findings from issues, and the intents. |
| `environments/`, `architecture/` | Hosts, ports, deployments; what calls what. |
| `metrics/` | One record per `/hga:issue` run: times, tokens, review rounds. `/hga:dashboard` charts them. |

## Changing something, or when something is off

- `/hga:init` — change any setting above (language, board, Slack, review provider, limits); it updates this page
  too.
- `/hga:init check` — checks the prerequisites and the setup, and offers to repair what it finds.
- `/hga:dashboard` — your dashboard on claude.ai of how the runs went (lead time, sections, tokens, an API-price
  cost estimate, review rounds), by repository and period; `/hga:dashboard refresh` brings in the newest runs.
- The panes: `/issue-pane`, `/triage-pane`, `/intent-pane` show or hide them; the skills work without them.

## Sources and verification

- Written by `/hga:init` on {{DATE}} from `hga.config.json` and the machine configuration.
