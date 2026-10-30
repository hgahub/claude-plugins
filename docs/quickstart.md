# Quickstart: from install to a reviewed pull request

This guide takes you from a fresh install to a pull request that hga implemented, tested and had reviewed. You
will do it on a small sample repository, so nothing in your own projects changes.

## You need

- Claude Code (`claude --version`).
- GitHub CLI, logged in (`gh auth status`).
- A GitHub account that can open pull requests on the sample repository (see step 2).

## 1. Install the plugin

In a terminal:

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Start Claude Code and run `/hga:init quick`. It sets up a local knowledge base with the defaults (status labels,
GitHub comments, local review) after at most two questions. Run `/hga:init` later to change any of it.

## 2. Get the sample repository

The sample is [hgahub/hga-demo](https://github.com/hgahub/hga-demo), a small todo app. Fork it to your account and
clone your fork:

```
gh repo fork hgahub/hga-demo --clone
cd hga-demo
```

Its issues are the work. We use **issue #2**, "Whitespace-only titles are accepted": `POST /api/todos` with a title
of spaces returns 201 and adds an empty row. The fix is to refuse it, the same way as an empty title, and to add a
test for it.

> Issue #1 already has an open pull request in the sample repository, so it is not the one to take here.

File the same issue in your fork (or copy its text from `hgahub/hga-demo`), then note its URL.

## 3. Run `/hga:issue` on it

From the `hga-demo` folder, in Claude Code:

```
/hga:issue https://github.com/<you>/hga-demo/issues/<n>
```

The run goes through its steps on its own: it claims the issue (a GitHub comment and an assignment, unless Slack is
set up), sets it to In Progress, works in a separate git worktree, runs the tests, starts the app and checks the
fix in your browser, opens a pull request, has it reviewed, and sets the issue to In review. Let it finish. It
may ask you a question if a decision is open; answer it or pick the default it offers.

## 4. What to check

- **The issue pane.** Run `/issue-pane` to see the 13 steps (0 to 12). Each step shows `✅` with its evidence.
  Look at step 5 (the tests, with their numbers) and step 6 (the live test verdict). A step that is skipped
  says why.
- **The pull request.** It closes the issue, and its description has the sections Tests, Live user test and Review.
- **The report.** The run ends with a report comment on the issue: the time, the difficulty, the token use and
  the checklist.
- **The knowledge base.** The run writes a metrics record under `metrics/` in your knowledge base, with the time
  and the tokens per issue. Use `/hga:dashboard` to see several runs together.

## Expected time and tokens

Measured on four runs of this plugin's own issues: 16 to 28 minutes of active work per issue, plus 1 to 2 minutes
of waiting for the review. Output tokens were 32,000 to 50,000 per run. Most of the total is the context re-read
on every call: 6 to 15 million cache-read tokens. The sample issue is smaller than those, so expect the lower end.
These numbers are an estimate from a few runs, not a promise.

## Next

- Write your own issue, or let `/hga:intent` turn a few sentences into one, then `/hga:triage` to prepare it.
- The full README: [plugins/hga/README.md](../plugins/hga/README.md).
