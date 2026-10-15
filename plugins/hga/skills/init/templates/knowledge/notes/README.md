# notes/

New, dated findings: one note per finding or per issue. This is where `/hga:issue` (step 11) and
`/hga:triage` write. Canonical pages elsewhere change only with evidence; a note can be written any time.

File name: `<app>-<issue>-<topic>.md` (e.g. `web-app-142-csv-export.md`), or `<app>-<topic>.md` without an
issue. The map (`map/<app>.md`) takes the app from the prefix and the issue from the number. Link related
notes with `[[file-name-without-extension]]`.

Template:

```markdown
---
title: "web-app #142: CSV export drops the trust column"
verified_at: "2026-01-31"
status: verified
review_after_days: 30
managed_by: claude-code-session
---

# web-app #142: CSV export drops the trust column

What was found, in a few sentences. Inferences are marked as such.

## Details
The mechanism (function and type names), measurements (date, commit, environment, steps, result).

## Sources and verification
- Code: `src/export.py` at abc1234
- Measured: `curl …/health` on 2026-01-31
- Issue / PR: https://github.com/owner/repo/issues/142, …/pull/151
```
