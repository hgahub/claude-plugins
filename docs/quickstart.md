# Quickstart: from install to a reviewed pull request

This guide takes you from a fresh install to a pull request that hga implemented, tested and had reviewed, in a
repository of your own. hga gives you no sample repository: you use one you already have, or create a small one for
the first run.

## You need

- Claude Code (`claude --version`).
- GitHub CLI, logged in (`gh auth status`).
- git, and Python 3.9 or newer. hga's scripts need both; `/hga:init` stops if either is missing.
- A GitHub repository you can push to, with Issues turned on and a test command that runs (step 2).
- A browser for the live test, only if the change has a UI or a server to check: the desktop app's built-in browser,
  or Claude in Chrome.

## 1. Install the plugin

In a terminal:

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Start Claude Code and run `/hga:init quick`. It sets up a local knowledge base with the defaults (status labels,
GitHub comments, local review) after at most two questions. Run `/hga:init` later to change any of it.

## 2. Pick a repository and file a small issue

Use a repository of yours that has tests, or create a new small one for the first run:

```
gh repo create hga-first-run --private --clone
cd hga-first-run
```

Add a small program and its tests, commit, and push them to the default branch. Whichever repository you use, write
its test command (`pytest`, `npm test`, …) in its README or `CLAUDE.md`, so the run finds it. A new repository has
Issues turned on; for an older one, check the repository's settings.

Then file one small, clearly reproducible issue yourself. A good first issue:

- touches **one module**, not a design across the codebase;
- has a **visible symptom**: a wrong output, an error, a value that should be refused;
- can be **caught by a test**, so the run can show that the test fails before the fix and passes after it.

For example, in an `issue.md` file:

```markdown
## Steps
1. Call `slugify("Hello  World")` (two spaces).

## Expected
`hello-world`

## Actual
`hello--world`
```

```
gh issue create --title "slugify() keeps double hyphens" --body-file issue.md
```

The command prints the URL of the new issue; you use it in step 3.

## 3. Run `/hga:issue` on it

From the repository's folder, in Claude Code:

```
/hga:issue https://github.com/<you>/<repo>/issues/<n>
```

The run goes through its steps on its own: it claims the issue (a GitHub comment and an assignment, unless Slack is
set up), sets it to In Progress, works in a separate git worktree, runs the tests, checks the fix live if the change
has a UI or a server, opens a pull request, has it reviewed, and sets the issue to In review. Let it finish. It may
ask your permission to run the tests, start an app server or open the browser; allow them. It may also ask a
question if a decision is open; answer it or pick the default it offers.

## 4. What to check

- **The issue pane.** Run `/issue-pane` to see the 13 steps (0 to 12). Each step has a mark and its evidence: `✅`
  done, `➖` not applicable to this change (a small fix usually has steps 4 and 11 so: nothing to decide, nothing new
  for the knowledge base), `⚠️` skipped, with the reason. Look at step 5 (the tests, with their numbers) and step 6
  (the live test verdict, or why it was skipped).
- **The pull request.** It closes the issue, and its description has the sections Tests, Live user test and Review
  (in the language `/hga:init` set).
- **The report.** The run ends with a report comment on the issue: the time, the difficulty, the token use and
  the checklist.
- **The knowledge base.** The run writes a metrics record under `metrics/` in your knowledge base, with the time
  and the tokens per issue. Use `/hga:dashboard` to see several runs together.

## Expected time and tokens

As of 2026-10-30, measured on five runs of this plugin's own issues: 7 to 28 minutes of active work per issue, plus
under 2 minutes of waiting for the review. Output tokens were 32,000 to 50,000 per run. Cache-read tokens, which make
up most of the total, were 6 to 15 million. None of these runs started an app or checked it in a browser; a change
with a live test takes longer. These numbers are an estimate, not a promise; `/hga:dashboard` shows the current
figures from your own runs.

## Next

- Let `/hga:intent` turn a few sentences into an issue, then `/hga:triage` to prepare it.
- The full README: [plugins/hga/README.md](../plugins/hga/README.md).
