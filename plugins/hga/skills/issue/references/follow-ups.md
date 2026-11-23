# 7a — follow-up issues, as GitHub issues, tracked

Read from `SKILL.md`, step 7a, when a finding is to become a follow-up issue.

1. Verify the claim on the current default branch (`git grep … origin/<default-branch>`), with file:line; record
   live-only findings as measurements (date, environment, data). If earlier text overstated it, fix that too.
2. Duplicate search (`--state all`); a related but different bug is linked as "related".
3. Body: a `**Ref:** #<n> / PR #<pr>` line, `## The bug`, `## What we measured`, `## Why it hurts`,
   `## Direction of the fix`, `## Acceptance criteria` (numbered, with the regression test). Label `bug` or what
   fits.
4. Never quote secrets or real people's data — describe what leaked and how much.
5. `HGA track <owner/repo> <n>` → `Status: Todo · issue: OPEN`.
6. Link it in the PR's "Not part of this PR", the report and the knowledge note.
