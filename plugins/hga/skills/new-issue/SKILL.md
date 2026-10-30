---
name: new-issue
description: Use when an intent.md from the hga knowledge base (written by /hga:intent) is to become a GitHub issue — the last step of /hga:intent, or on its own ("create the issue from this intent", "turn this intent into an issue", "file this intent"). Gates the intent with intent_check.py, checks for duplicates, writes the issue body from the intent's sections, creates and reads it back, puts it on the project board (Todo) with its type, and writes the issue number back into the intent. Leaves the triage label to /hga:triage. Works for any GitHub repository.
user-invocable: true
argument-hint: "<path to the intent.md | <app>-intent-<topic>> [--comment owner/repo#n]"
---

# New issue from an intent

Makes a GitHub issue from an accepted intent.md. It goes on the board untriaged (no state label), so
`/hga:triage`'s branch C finds it and its branch A starts from the intent.

- `HGA` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/issue/scripts/hga_issue.py"`,
  `ICHK` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/intent/scripts/intent_check.py"` (`python` on Windows). Spell
  them out in every Bash call — a shell variable does not split in zsh.
- `K` = `knowledge_dir` from `HGA config` (default `~/.hga/knowledge`); `language` there is the issue's language.

## Steps

1. **The intent:** the given path, or `K/notes/<name>.md`. Its frontmatter `repo` is the target repository. A
   non-empty `issue` means the issue exists: stop and give its link.
2. **Gate:** `ICHK <file>`. BLOCK → no issue: report the error codes and send the user back to `/hga:intent`.
   WARN → the warnings also go into "Open questions".
3. **Approval:** called from `/hga:intent` station 5, the author already approved — do not ask again. On its own,
   ask: the repository, the title, the number of criteria — "May I create the issue?".
4. **Duplicate:** `gh issue list --repo <owner/repo> --state open --search "<2–3 keywords>"`. If an open issue
   wants the same thing and the author has not already chosen a separate one, ask: comment on it (`--comment`
   mode) or a new issue.
5. **Title:** imperative or a noun phrase, ≤70 characters, from the "Desired outcome" (e.g. "Excel export: show
   the source column"), without the app's name.
6. **Body** (scratchpad file, passed with `--body-file`), the intent's sections taken over unedited, in order:
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
   The link: with a GitHub remote on the knowledge base (`git -C "$K" remote get-url origin`),
   `[<intent>](https://github.com/<kb-owner>/<kb-repo>/blob/<branch>/notes/<intent>.md)`; otherwise
   `` `notes/<intent>.md` ``. "Clarification log" and "Sources" stay in the knowledge base. Leave out empty
   sections. If you find secret or personal data, stop and say so.
7. **Create and read back:** `gh issue create --repo <owner/repo> --title "<title>" --body-file <file>`, then
   `gh issue view <n> --repo <owner/repo> --json title,body` must match. `--comment` mode: `gh issue comment <n> --repo <owner/repo> --body-file <file>`
   with the body starting "Addition from the intent:", read back with `--json comments`.
8. **Board and type** (new issue): `HGA track <owner/repo> <n>` (Todo; without a board, Todo is no status
   label), then `HGA meta <owner/repo> <n> --type <T>` — `Bug` if "Current state" describes a measured deviation,
   `Feature` for a new capability, `Task` otherwise. Skip `n/a` fields. Priority, Effort, iteration and the
   state label are the triage's.
9. **Back into the intent:** frontmatter `issue: <owner/repo>#<n>`, `intent_status: issue`, ` (#<n>)` at the end
   of `title` (the map links it to later notes). Commit with `kb_commit.py` as `hga:knowledge` says
   (`<app>: intent → #<n>`).
10. **Report:** the issue's link, the `HGA meta` line, the ICHK verdict, and the next step
    `/hga:triage <issue URL>`. With the `mcp__hga__intent` tool, report the `issue` field.

**Done** when the issue (or comment) is read back, it is Todo on the board (if there is one), and the intent with
the issue number is committed (and pushed, with a remote).

## Boundaries

- One call, one issue. If the intent looks too big for one, say so in the report: splitting is the triage's
  (`/hga:triage`, branch B, point 2a) — do not split it yourself.
- No Slack message, label, milestone or assignee.
