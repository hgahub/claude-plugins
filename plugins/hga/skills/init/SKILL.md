---
name: init
description: Use to set up the hga plugin on a machine or for a team — check the prerequisites, create a new knowledge base (local folder, optionally a private GitHub repository) or join the team's existing one, and write the team and user configuration (language, time zone, GitHub project board, closing, Slack channel, review provider, parallel limits, live-test browser, risk-class patterns), and write a short usage guide in the team's language (a knowledge base page, optionally a Docs copy). Also re-run it to check or repair a setup. Triggers include "set up hga", "initialize the knowledge base", "hga init", "join our knowledge base", "configure the issue workflow", "change the review provider".
user-invocable: true
argument-hint: "[new | join <git URL> | check]"
---

# Setup

`/hga:issue`, `/hga:triage` and `/hga:knowledge` need a knowledge base and a configuration. This skill creates
both, step by step, and can be re-run any time: if something already exists, it shows it and only fills in what
is missing. It never overwrites a non-empty folder or an existing configuration without asking.

`HGA` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/issue/scripts/hga_issue.py"` (`python` on Windows; spell it out in
every Bash call — a shell variable does not split in zsh). `INIT` = `${CLAUDE_PLUGIN_ROOT}/skills/init`,
`KB` = `${CLAUDE_PLUGIN_ROOT}/skills/knowledge/scripts`.

Configuration has two layers (`HGA config` prints the merged result, with the files it came from):

| Layer | File | Holds |
|---|---|---|
| Team | `<knowledge_dir>/hga.config.json` — versioned with the knowledge base, shared | language, time zone, project board, labels and closing, Slack, review provider, parallel limits, live-test browser, risk patterns |
| Machine | `~/.claude/hga/config.json` | `knowledge_dir` (default `~/.hga/knowledge`), `guide_doc_url` (this user's Docs copy of the guide, step 7), `dashboard_url` (this user's metrics dashboard, written by `/hga:dashboard`), and any team field to override for this machine |

Ask every choice with `AskUserQuestion`, after detecting what you can so the options are real values. With an
argument, skip the matching question: `new`, `join <URL>`, or `check` (steps 1, 6, 7 and 8 only).

## 1. Prerequisites

Run `HGA doctor` and show its table. Before the first setup, the knowledge base and the configuration rows say
"not set up yet — run /hga:init": that is expected, steps 2–4 create them. Required: Python 3.9+, git, `gh` logged in with the `repo` scope,
and the `code-review` skill — every PR's review runs it, whatever `review.provider` is (`/hga:issue` step 8).
`doctor` cannot see skills: check this session's skill list yourself, and add the line to the table (`ok` or
`MISSING · comes with Claude Code: claude update, then a new session`). Optional:
`uv` (live tests of Python apps), the `project` scope (only with a project board: `gh auth refresh -s project`),
`tzdata` on Windows (`pip install tzdata`, for a named time zone). Also check, and report as optional:

- a Slack MCP connector (any `slack_read_channel` / `slack_send_message` tool in the session);
- a browser for live tests: Claude in Chrome (`mcp__claude-in-chrome__*`) or the built-in browser
  (`mcp__Claude_Browser__*`).

If a required item is missing, give the fix command and stop until the user has fixed it. Do not install
anything yourself.

## 2. Knowledge base

Read the machine layer first (`HGA config` → `knowledge_dir`, `sources.user`). Ask where the knowledge base
should live if there is no machine configuration yet (default `~/.hga/knowledge`). Then:

- **The folder exists and has `hga.config.json`** → it is set up. Show `git -C <dir> remote -v` and
  `git -C <dir> status --short`, and go on to step 3.
- **Otherwise ask:** "New knowledge base" or "Join the team's knowledge base".

**New:**

1. `python3 "$INIT/scripts/scaffold_kb.py" <dir>` — creates the skeleton from `templates/knowledge/` with today's
   date. Exit 3 means the folder is not empty: show what is in it, and ask whether to add only the missing files
   (`--add-missing`) or to choose another folder. Never delete or move the user's files.
2. If `<dir>/.git` does not exist yet: `git -C <dir> init`, then `git -C <dir> symbolic-ref HEAD refs/heads/main`
   (the same as `git init -b main`, which git before 2.28 does not have). Leave an existing repository as it is.
3. Ask where the shared copy should live:
   - **"Private GitHub repository (Recommended for a team)"** — others join with its URL. Ask for the owner and
     the name (default `<user>/knowledge`), confirm, then `gh repo create <owner>/<name> --private --source <dir>`.
   - **"Another git host"** (GitLab, Bitbucket, the company's server) — the user creates an empty private
     repository there and gives its URL; then `git -C <dir> remote add origin <URL>`. Credentials are the user's
     git setup; the push in step 4 proves access.
   - **"Local only"** — no remote; re-running `/hga:init` can add one later.

   No push yet: step 4 commits first.

**Join:**

1. Ask for the git URL (or take it from the argument) — any git host works. `git clone <URL> <dir>` — only into a
   missing or empty folder.
2. If the clone has no `hga.config.json`, it is a new team setup: step 4 asks the team questions, and the commit
   goes to the shared repository — say so before writing.

## 3. Machine configuration

Do this before the team configuration: `HGA config` and `HGA doctor` find the knowledge base through this file,
so without it step 4 would check the default folder instead of `<dir>`.

Write `~/.claude/hga/config.json` with `{"knowledge_dir": "<dir>"}` if the folder is not the default or the file
does not exist yet. Keep any existing keys: read it first, change only `knowledge_dir`. Overrides of team fields
go here only if the user asks for them. Then `HGA config` must print `"knowledge_dir": "<dir>"`.

## 4. Team configuration

Skip this step if `<dir>/hga.config.json` exists, unless the user asked to change it (then show the current
values and ask only about the changes). Otherwise start from `$INIT/templates/hga.config.json` and ask:

1. **Language** of everything the plugin writes outward (commits, PRs, issues, Slack, notes): `en`
   (Recommended); the language of this conversation, if it is not English (its code, e.g. `de`); or another
   language code the user names.
2. **Time zone:** the system's (`null`, Recommended), or an IANA name (e.g. `Europe/Berlin`) when the team spans
   time zones and "today" must be the same for everyone.
3. **GitHub project board:** list the owner's boards
   (`gh project list --owner <owner> --format json`). Options: "No board — status labels (Recommended for a
   start)", or one of the boards. For a board, read its fields
   (`gh project field-list <number> --owner <owner> --format json`): it needs a single-select status field with
   options for to-do, in progress, in review and done; map their names into `github.fields.status` and
   `github.statuses`. No in-review option: offer to add one on the board (Recommended), or map `in_review` to the
   done option (one status for both, the behavior before 1.0). Recommend the board's built-in "Item closed"
   workflow (→ Done).
   Iteration, Priority and Effort are used only if they exist.
4. **Closing** (`labels.closing`): "GitHub's own — the PR's `Closes #n` closes the issue at merge
   (Recommended)" (`null`), or "The maintainer's label": the PR only says `Ref #n`, the merge leaves the issue
   open, and the maintainer closes it with a label after the merge (ask for its name, e.g. `done`). The label
   counts as closed for prerequisites and hides the issue from `/hga:triage`'s groups; the agent never adds it
   and never closes the issue. Check that the label exists in the repositories the user names
   (`gh label list --repo <owner/repo>`); offer to create it in step 5.
5. **Slack:** "No Slack — claims and reports as GitHub comments (Recommended without a Slack connector)", or a
   channel. For a channel, find it with the Slack tools (`slack_search_channels`), confirm the name, and store
   `{"channel": "#name", "channel_id": "C…"}`. Read one message from it (`slack_read_channel`, limit 1) to prove
   access; if that fails, say so and store nothing.
6. **Review provider:** "Local code-review only (Recommended)", "Codex", "Copilot", "Greptile". A bot reviews in
   addition to the local review, not instead of it. The bot must be installed on the repositories (Codex and
   Greptile as GitHub apps; Copilot code review enabled for the account or organization): say so, and if the
   user names a repository, check whether the bot ever reviewed a PR there
   (`gh api repos/<o>/<r>/pulls?state=all&per_page=20` + their reviews' authors) — report what you found, do
   not block on it. Copilot and Greptile support is newer: mention it.
7. **Review round limit** (`review.ask_after_rounds`): 5 (Recommended), or the user's number. From this round on,
   `/hga:issue` asks the maintainer whether to close the review — the local review's rounds count too.
8. **Parallel limits** (for `/hga:triage`'s launches): at most 2 running implementations per repository and an
   80% ceiling on the 5-hour plan usage (Recommended), or the user's numbers.
9. **Live-test browser** (`live_test.browser`): "The built-in browser of the desktop app (Recommended)"
   (`builtin`) or "Claude in Chrome" (`chrome`) — which one `/hga:issue`'s live test tries first; it falls back to
   the other one when the first is not in the session.
10. **Risk classes** (`risk`): `/hga:issue` classifies each change from its files — `high` if a file matches
   `high_paths` (or the issue has `high_label`), `low` if every file matches `low_paths`, `standard` otherwise —
   and the class decides which gates the run needs (a docs-only change gets no live test and no bot review; a
   migration needs the maintainer's decision and a rollback note). Show the defaults from the template first.
   A pattern without `/` matches the file name anywhere; with `/`, the path from the repository root (`**` spans
   folders).
   - **High-risk paths:** "The defaults (Recommended)" — migrations, `*.sql`, auth, permissions, CI workflows —
     or the defaults plus the team's own (payments, infrastructure, secrets handling…). A team list replaces the
     default one, so keep the defaults in it unless the user drops one on purpose.
   - **Per-repository low paths:** ask whether a repository's files that look like docs are in fact runtime —
     e.g. one whose `*.md` files are prompts or skills, or whose `*.txt` files are data the app loads. For each
     one the user names, store `repos.<owner/repo>.low_paths` with only what really is safe there (e.g.
     `["docs/**", "tests/**"]`): it **replaces** the team's low list for that repository. A repository may also
     add `high_paths` (it adds to the team's, never removes one). "None for now (Recommended)" leaves
     `repos` empty.
   - `high_label`: `risk:high` (Recommended) — the label that raises any issue to high.

Write the file with `Write`, then read it back through the plugin:

- `HGA config` must show `sources.team` = `<dir>/hga.config.json` and the values just chosen — if it shows the
  defaults, step 3's machine configuration is missing or points elsewhere: fix that first;
- `HGA doctor` must show no "configuration" problem.

Then commit it with the skeleton:

```bash
python3 "$KB/kb_commit.py" -C <dir> -m "Set up the knowledge base (hga)" -- .   # a fresh one: only the skeleton and the configuration
```

For an existing, shared knowledge base, commit only `hga.config.json` (`-- hga.config.json`, not `.`), and say
before running it that it changes the team's settings. The helper validates, commits under the knowledge
base's lock and pushes (setting the upstream on the first push). Exit `5` means the push failed: show git's
error from its output — on another host it is usually the user's credentials, which they fix themselves.

## 5. Optional, one question each

- **Standing permission for the Slack claim** (only with Slack): show `$INIT/templates/claude-md-snippet.md`
  filled in with the channel, and ask whether to append it to `~/.claude/CLAUDE.md`. It lets `/hga:issue` post
  the claim and the final report in that channel without asking each time; everything else still needs approval.
  Append it only on an explicit yes, and never edit other parts of the file.
- **Triage labels** in repositories the user names: `ready-for-agent`, `ready-for-human`, `needs-info`, the
  status labels (`in-progress`, `in-review`, without a board), and the closing label (with `labels.closing`). `HGA triage-state` and `HGA status-set` also create
  them on first use, so this is only for seeing them up front: `gh label create <name> --repo <owner/repo>
  --color <hex> --description "<…>"`, skipping existing ones.
- **A first app page:** if the user names an application, create `apps/<app>.md` from the template in
  `apps/README.md` with what you can verify now (repository, default branch, how to run the tests), and a
  `workflow/<app>.md` stub — step 8 validates and commits them.

## 6. Repair

On a re-run, and always with `check`: go through what `HGA doctor` (step 1) reported, and fix only on the user's
yes — one question per item.

- **`MISSING] knowledge base`** with a machine configuration → the folder was moved or deleted. Ask: point
  `knowledge_dir` at the right folder (step 3), clone the team's knowledge base again (step 2, Join), or create
  a new one (step 2, New).
- **`MISSING] configuration`** → show the field, the file it comes from (`HGA config` → `sources`; a machine
  override wins over the team file) and the problem; ask step 4's question for that field, write only that
  field, and check again.
- **No `risk` in the team file** (written by an older plugin version) → the defaults apply, which is not an
  error. Offer step 4's question 10 once; on a yes, write only the `risk` key.
- **No `labels.closing` or `live_test` in the team file** (older plugin version) → the defaults apply (GitHub's
  own closing, the built-in browser). Offer step 4's questions 4 and 9 once; on a yes, write only those keys.
- **`labels.closed`** → no longer used (versions before 0.4 wrote it). Ask whether the team closes issues with
  that label: on a yes, move its value to `labels.closing`; otherwise remove the key. Only that key, in the file
  that has it (read both layers).
- **Template files the knowledge base lacks** (newer plugin versions add some):
  `python3 "$INIT/scripts/scaffold_kb.py" <dir> --add-missing --dry-run` lists them without writing. Show the
  list and ask — the team may have deleted a page on purpose — then run it without `--dry-run`.

A change to the shared knowledge base is committed with only the files it touched (never `.`), and before
running it say that it changes the team's knowledge base or settings:

```bash
python3 "$KB/kb_commit.py" -C <dir> -m "Repair the hga setup: <what> (hga)" -- <the changed files>
```

## 7. Guide

A short page on how the team uses hga, with its own settings filled in: `<dir>/workflow/hga-guide.md`, from
`$INIT/templates/guide.md` (the comment at its top says how to fill it in; it does not go into the page).

- **When:** write it if it does not exist yet, or if this run wrote or changed the team configuration. Otherwise
  (and always with `check`) compare its settings table with `HGA config`: if they differ, offer to rewrite it.
  If its frontmatter no longer says `managed_by: hga-init`, the team has taken it over: show the differences
  and ask, never overwrite it silently.
- **How:** in the configured `language`, only the lines that match the configuration, the page starting with
  its frontmatter (`verified_at` = today). Keep it as short as the template. Step 8 validates and commits it.

**Docs copy** (an editable, shareable document on claude.ai):

- Only if this session has the Claude Docs connector (a `docs` skill is listed, or the Artifact tool lists a
  "Docs" type); otherwise skip, and say the knowledge base page is the guide.
- **`guide_doc_url` set** (machine configuration): load the `docs` skill, read that doc and bring it in line
  with the page — text the page lacks (someone edited the doc) is shown and asked about before replacing. If the
  doc is gone or not editable, ask whether to make a new one.
- **Not set:** ask "Docs copy of the guide" or "Only the knowledge base page". On yes, create the doc with the
  `docs` skill from the page's title and body (no frontmatter, no "Sources"), then write its URL into
  `~/.claude/hga/config.json` as `guide_doc_url` (keep the other keys).
- With the link, say that the knowledge base page is the source: `/hga:init` refreshes the doc from it.

## 8. Check

```bash
python3 "$KB/validate_kb.py" "<dir>"
HGA config
HGA doctor --repo <owner/repo>   # with a board: a repository of the board's owner, so its status options are checked
```

All must succeed (warnings allowed). If step 5 or 7 wrote pages, commit them (only those files; the helper
rebuilds the map and validates first, and pushes if the knowledge base has a remote) — for a shared knowledge
base, say first that the team will see them:

```bash
python3 "$KB/kb_commit.py" -C <dir> -m "The hga guide and first app pages (hga)" -- workflow/hga-guide.md apps/<app>.md workflow/<app>.md   # whichever were written
```

Then summarize in a short table: knowledge base (folder, remote), team
configuration (language, board or labels, closing, Slack or GitHub comments, review provider and round limit,
limits, live-test browser, risk patterns and per-repository overrides),
machine configuration, the guide (page, Docs link), what was repaired, what was skipped and why. End with the next step: "Try
`/hga:triage <owner/repo>` or `/hga:issue <issue URL>`." Mention that `/hga:init` can be re-run to change any of
this.
