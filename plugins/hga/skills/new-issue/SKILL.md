---
name: new-issue
description: Use when an intent.md from the hga knowledge base (written by /hga:intent) is to become a GitHub issue — the last step of /hga:intent, or on its own ("create the issue from this intent", "turn this intent into an issue", "file this intent"). Gates the intent with intent_check.py, checks for duplicates, writes the issue body from the intent's sections, creates and reads it back, puts it on the project board (Todo) with its type, and writes the issue number back into the intent. Leaves the triage label to /hga:triage. Works for any GitHub repository.
user-invocable: true
argument-hint: "<path to the intent.md | <app>-intent-<topic>> [--comment owner/repo#n]"
---

# New issue from an intent

Makes a GitHub issue from an accepted intent.md. The issue is the triage's input: it goes on the board
untriaged (without a state label), so branch C of `/hga:triage` finds it, and its branch A starts from the
intent.

- `HGA` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/issue/scripts/hga_issue.py"` (on Windows `python`)
- `ICHK` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/intent/scripts/intent_check.py"`
- `K` = `knowledge_dir` from `HGA config` (default `~/.hga/knowledge`; the file tools need the expanded absolute
  path). `language` from the same output is the issue's language.

Write the helpers out in full in every Bash call, or define shell functions first — a shell variable does not
work (zsh does not split it into words).

## Steps

1. **The intent.** The given path, or `K/notes/<name>.md`. Read it through: the frontmatter's `repo` field is
   the target repository, and its `issue` field is empty (if not, the issue exists already: stop, and give its
   link).
2. **Readiness gate:** `ICHK <file>`. On BLOCK there is no issue: the report lists the error codes, and sends
   the user back to `/hga:intent`. On WARN the warnings also go into the issue's "Open questions" section.
3. **Approval.** Called from station 5 of `/hga:intent`, the author has already approved the issue: do not ask
   again. Called on its own, `AskUserQuestion`: the repository, the title and the number of criteria — "May I
   create the issue?".
4. **Duplicate:** `gh issue list --repo <owner/repo> --state open --search "<2–3 keywords from the title>"`. If
   an open issue wants the same thing, and the author has not already decided on a separate issue, ask:
   a comment on the existing one (`--comment` mode) or a new issue.
5. **Title:** imperative or a noun phrase, at most 70 characters, from the "Desired outcome" (e.g. "Excel
   export: show the source column"). The app's name is not needed in it.
6. **Body** (`Write` to the scratchpad, from there `--body-file`), taken over from the intent's sections without
   editing, in this order:
   ```
   **Intent:** <link to the note> · <verified_at> · <author>

   > <the Intent quote>

   ## Problem
   ## Desired outcome
   ## Affected users and systems
   ## Current state
   ## Expected behavior
   ## Acceptance criteria
   ## Constraints
   ## Out of scope
   ## Decisions
   ## Open questions          + the ICHK warnings, on WARN
   ```
   The link: if the knowledge base has a GitHub remote (`git -C "$K" remote get-url origin`), the note's URL on
   it — `[<intent>](https://github.com/<kb-owner>/<kb-repo>/blob/<branch>/notes/<intent>.md)`; otherwise the
   path in code, `` `notes/<intent>.md` ``. The "Clarification log" and the "Sources" stay in the knowledge base
   (the link points there). An empty section is left out. No secret or personal data may be in it — if you find
   some anyway, stop, and say so.
7. **Create and read back:**
   - new issue: `gh issue create --repo <owner/repo> --title "<title>" --body-file <file>`; the number from the
     output's URL, then `gh issue view <n> --repo <owner/repo> --json title,body`: the title and the body match;
   - `--comment` mode: `gh issue comment <n> --repo <owner/repo> --body-file <file>`, the body starting with
     "Addition from the intent:"; read back with `gh issue view <n> --repo <owner/repo> --json comments`.
8. **Board and type** (for a new issue): `HGA track <owner/repo> <n>` (Todo; with status labels instead of a
   board, Todo is the absence of a status label), then `HGA meta <owner/repo> <n> --type <T>` — `Bug`
   if the "Current state" describes a measured deviation from the expected behavior; `Feature` if it asks for a
   new capability; `Task` otherwise. Fields shown as `n/a` do not exist for this owner: skip them. Priority,
   Effort, the iteration and the state label belong to the triage; do not set them.
9. **Back into the intent:** frontmatter `issue: <owner/repo>#<n>`, `intent_status: issue`, ` (#<n>)` at the end
   of the `title` (so the map links it to the issue's later notes). Then commit it (`<app>: intent → #<n>`)
   with `kb_commit.py`, as `hga:knowledge` says: it rebuilds the map, validates, commits and pushes.
10. **Report:** the issue's link, the `HGA meta` line, the ICHK verdict, and the next step:
    `/hga:triage <issue URL>`. If the session has the `mcp__hga__intent` tool, report with the `issue` field.

**Done** when the issue (or the comment) exists read back, it is Todo on the board (where there is one), and the
intent with the issue number is in the knowledge base (pushed, if it has a remote).

## Boundaries

- One call, one issue. If the intent is too big for one issue ("Out of scope" follow-ups, several independent
  groups of criteria), say so, and propose splitting it in `/hga:intent` — do not split it on your own.
- No Slack message, label, milestone or assignee comes with it.
