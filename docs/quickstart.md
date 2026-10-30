# Quickstart: from install to a reviewed pull request

This guide takes you from a fresh install to a pull request that hga implemented, tested and had reviewed. You
will do it on a small sample repository, so nothing in your own projects changes.

## You need

- Claude Code (`claude --version`).
- GitHub CLI, logged in (`gh auth status`), with any GitHub account: the work happens in your own fork (step 2).
- Python 3.9 or newer, and git. hga's scripts need both; `/hga:init` stops if either is missing.
- `uv`, which the sample repository uses to install, test and run its app.
- A browser for the live test: the desktop app's built-in browser, or Claude in Chrome. Without one, the run's live
  test ends `NOT VERIFIED`.

## 1. Install the plugin

In a terminal:

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Start Claude Code and run `/hga:init quick`. It sets up a local knowledge base with the defaults (status labels,
GitHub comments, local review) after at most two questions. Run `/hga:init` later to change any of it.

## 2. Get the sample repository

The sample is [hgahub/hga-demo](https://github.com/hgahub/hga-demo), a small todo app. Fork it to your account,
clone your fork, and file the issue you will work on in your fork:

```
gh repo fork hgahub/hga-demo --clone
cd hga-demo
gh repo set-default <you>/hga-demo
gh repo edit --enable-issues
gh issue view 2 --repo hgahub/hga-demo --json body -q .body | gh issue create --title "Whitespace-only titles are accepted" --body-file -
```

`gh repo set-default` makes your fork the repository `gh` uses in this folder, because `gh repo fork --clone` also
adds an `upstream` remote, and `gh` may otherwise pick the parent. `gh repo edit --enable-issues` turns Issues on,
since forks have them off by default. The last command prints the URL of the new issue; you use it in step 3.

The issue is a bug: `POST /api/todos` with a title of spaces returns 201 and adds an empty row. The fix is to refuse
it, the same way as an empty title, and to add a test for it.

## 3. Run `/hga:issue` on it

From the `hga-demo` folder, in Claude Code:

```
/hga:issue https://github.com/<you>/hga-demo/issues/<n>
```

The run goes through its steps on its own: it claims the issue (a GitHub comment and an assignment, unless Slack is
set up), sets it to In Progress, works in a separate git worktree, runs the tests, starts the app and checks the
fix in your browser, opens a pull request, has it reviewed, and sets the issue to In review. Let it finish. The run
may ask your permission to start the app server and to open the browser; allow both, the live test needs them. It
may also ask a question if a decision is open; answer it or pick the default it offers.

## 4. What to check

- **The issue pane.** Run `/issue-pane` to see the 13 steps (0 to 12). Each step has a mark and its evidence: `✅`
  done, `➖` not applicable to this change (a small fix usually has two, e.g. step 4 when nothing was decided), `⚠️`
  skipped, with the reason. Look at step 5 (the tests, with their numbers) and step 6 (the live test verdict).
- **The pull request.** It closes the issue, and its description has the sections Tests, Live user test and Review
  (in the language `/hga:init` set).
- **The report.** The run ends with a report comment on the issue: the time, the difficulty, the token use and
  the checklist.
- **The knowledge base.** The run writes a metrics record under `metrics/` in your knowledge base, with the time
  and the tokens per issue. Use `/hga:dashboard` to see several runs together.

## Expected time and tokens

As of 2026-10-30, measured on five runs of this plugin's own issues, not on the sample: 7 to 28 minutes of active work per issue, plus
under 2 minutes of waiting for the review. Output tokens were 32,000 to 50,000 per run. Cache-read tokens, which make
up most of the total, were 6 to 15 million. The sample run adds an app start and a browser check, which these
figures do not include, so its time and tokens are not measured yet. These numbers are an estimate, not a promise; `/hga:dashboard` shows
the current figures from your own runs.

## Next

- Write your own issue, or let `/hga:intent` turn a few sentences into one, then `/hga:triage` to prepare it.
- The full README: [plugins/hga/README.md](../plugins/hga/README.md).
