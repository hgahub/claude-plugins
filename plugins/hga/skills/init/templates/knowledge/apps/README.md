# apps/

One page per application, named after it (`web-app.md`). The file name is also the prefix of the app's notes
(`notes/web-app-142-csv-export.md`), so keep it short and stable.

Template:

```markdown
---
title: "web-app"
verified_at: "2026-01-31"
status: verified
review_after_days: 30
managed_by: claude-code-session
---

# web-app

What it is and who uses it, in two sentences.

## Repository
owner/repo, main branch, language and framework, where the conventions are documented.

## Build, run, test
Install command, start command and port, test command, the full gate before a PR.

## Environments
Where it runs (links to environments/), how it is deployed, health endpoints.

## Open decisions
Decisions waiting for someone, with the issue links.

## Sources and verification
What was read (file + commit SHA), what was measured (command + date), which issues.
```
