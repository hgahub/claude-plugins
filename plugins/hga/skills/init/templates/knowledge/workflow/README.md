# workflow/

App-specific pages for `/hga:issue`: whatever is particular to one repository. Where a page differs from the
skill's general description, the page wins. One page per app (`web-app.md`); a page may point to topic files
(`web-app/live-test.md`) when it grows. Keep each page short: past ~100 lines, split it into topic files.

`hga-guide.md` is not an app page: it is the team's short guide to using hga, written and refreshed by
`/hga:init` from the configuration.

Useful sections:

- **Gate** — the full check before a PR (e.g. `just check`, `npm test && npm run lint`), and what to record.
- **Install in a worktree** — the setup command for a fresh worktree.
- **Live test** — the start command and port, environment overrides (e.g. auth off), how to log in, which
  state objects to read with JavaScript, where the server log is. The command must run the **worktree's** code
  (`preview_start` runs it in the main checkout): give the flag that points it there (`--app-dir <worktree>`,
  `--prefix <worktree>`, `cd <worktree> && …`), and a quick way to prove it (a log line, or a request whose answer
  the fix changes).
- **Test data** — safe fixtures or accounts for live tests (names only, no secrets).
- **Pitfalls** — recurring traps not visible from the code.

Two placeholders are used because nothing is substituted here: `<SCRIPTS>` = the issue skill's `scripts/`
folder (it has `run_worktree.py`, an optional helper for Python apps), `<REPOS>` = the common parent folder of
the repositories' main checkouts (worktrees go next to them).
