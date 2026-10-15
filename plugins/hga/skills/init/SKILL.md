---
name: init
description: Use to set up the hga plugin on a machine or for a team — check the prerequisites, create a new knowledge base (local folder, optionally a private GitHub repository) or join the team's existing one, and write the team and user configuration (language, time zone, GitHub project board, Slack channel, review provider, parallel limits). Also re-run it to check or repair a setup. Triggers include "set up hga", "initialize the knowledge base", "hga init", "join our knowledge base", "configure the issue workflow", "change the review provider".
user-invocable: true
argument-hint: "[new | join <git URL> | check]"
---

# Setup

`/hga:issue`, `/hga:triage` and `/hga:knowledge` need a knowledge base and a configuration. This skill creates
both, step by step, and can be re-run any time: if something already exists, it shows it and only fills in what
is missing. It never overwrites a non-empty folder or an existing configuration without asking.

`HGA` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/issue/scripts/hga_issue.py"` (on Windows `python`).
`INIT` = `${CLAUDE_PLUGIN_ROOT}/skills/init`, `KB` = `${CLAUDE_PLUGIN_ROOT}/skills/knowledge/scripts`.

Configuration has two layers (`HGA config` prints the merged result, with the files it came from):

| Layer | File | Holds |
|---|---|---|
| Team | `<knowledge_dir>/hga.config.json` — versioned with the knowledge base, shared | language, time zone, project board, labels, Slack, review provider, parallel limits |
| Machine | `~/.claude/hga/config.json` | `knowledge_dir` (default `~/.hga/knowledge`), and any team field to override for this machine |

Ask every choice with `AskUserQuestion` (the recommended option first, "(Recommended)"); detect what you can
first, so the questions offer real values. With an argument, skip the matching question: `new`, `join <URL>`,
or `check` (steps 1 and 6 only).

## 1. Prerequisites

Run `HGA doctor` and show its table. Required: Python 3.9+, git, `gh` logged in with the `repo` scope. Optional:
`uv` (live tests of Python apps), the `project` scope (only with a project board: `gh auth refresh -s project`),
`tzdata` on Windows (`pip install tzdata`, for a named time zone). Also check, and report as optional:

- a Slack MCP connector (any `slack_read_channel` / `slack_send_message` tool in the session);
- a browser for live tests: Claude in Chrome (`mcp__claude-in-chrome__*`) or the built-in browser
  (`mcp__Claude_Browser__*`);
- the `code-review` skill (the default reviewer).

If a required item is missing, give the fix command and stop until the user has fixed it. Do not install
anything yourself.

## 2. Knowledge base

Read the machine layer first (`HGA config` → `knowledge_dir`, `sources.user`). Ask where the knowledge base
should live if there is no machine configuration yet (default `~/.hga/knowledge`). Then:

- **The folder exists and has `hga.config.json`** → it is set up. Show `git -C <dir> remote -v` and
  `git -C <dir> status --short`, and go on to step 4.
- **Otherwise ask:** "New knowledge base" or "Join the team's knowledge base".

**New:**

1. `python3 "$INIT/scripts/scaffold_kb.py" <dir>` — creates the skeleton from `templates/knowledge/` with today's
   date. Exit 3 means the folder is not empty: show what is in it, and ask whether to add only the missing files
   (`--add-missing`) or to choose another folder. Never delete or move the user's files.
2. `git -C <dir> init -b main`.
3. Ask whether to put it on GitHub as a **private** repository (recommended for a team; others join with its
   URL). If yes, ask for the owner and the name (default `<user>/knowledge`), confirm, then
   `gh repo create <owner>/<name> --private --source <dir>` (no push yet: step 3 commits first).

**Join:**

1. Ask for the git URL (or take it from the argument). `git clone <URL> <dir>` — only into a missing or empty
   folder.
2. If the clone has no `hga.config.json`, it is a new team setup: step 3 asks the team questions, and the commit
   goes to the shared repository — say so before writing.

## 3. Team configuration

Skip this step if `<dir>/hga.config.json` exists, unless the user asked to change it (then show the current
values and ask only about the changes). Otherwise start from `$INIT/templates/hga.config.json` and ask:

1. **Language** of everything the plugin writes outward (commits, PRs, issues, Slack, notes): `en`
   (Recommended), or another language code the user names.
2. **Time zone:** the system's (`null`, Recommended), or an IANA name (e.g. `Europe/Berlin`) when the team spans
   time zones and "today" must be the same for everyone.
3. **GitHub project board:** list the owner's boards
   (`gh project list --owner <owner> --format json`). Options: "No board — status labels (Recommended for a
   start)", or one of the boards. For a board, read its fields
   (`gh project field-list <number> --owner <owner> --format json`): it needs a single-select status field with
   options for to-do, in progress and done; map their names into `github.fields.status` and `github.statuses`.
   Iteration, Priority and Effort are used only if they exist.
4. **Slack:** "No Slack — claims and reports as GitHub comments (Recommended without a Slack connector)", or a
   channel. For a channel, find it with the Slack tools (`slack_search_channels`), confirm the name, and store
   `{"channel": "#name", "channel_id": "C…"}`. Read one message from it (`slack_read_channel`, limit 1) to prove
   access; if that fails, say so and store nothing.
5. **Review provider:** "Local code-review only (Recommended)", "Codex", "Copilot", "Greptile". For a bot, the
   bot must be installed on the repositories (Codex and Greptile as GitHub apps; Copilot code review enabled
   for the account or organization): say so, and if the user names a repository, check whether the bot ever
   reviewed a PR there (`gh api repos/<o>/<r>/pulls?state=all&per_page=20` + their reviews' authors) — report
   what you found, do not block on it. Copilot and Greptile support is newer: mention it.
6. **Parallel limits** (for `/hga:triage`'s launches): at most 2 running implementations per repository and an
   80% ceiling on the 5-hour plan usage (Recommended), or the user's numbers.

Write the file with `Write`, then `HGA config` must print it back without errors, and `HGA doctor` must show no
"configuration" problem. Then commit it with the skeleton:

```bash
git -C <dir> add -A        # a fresh knowledge base: only the skeleton and the configuration are in it
git -C <dir> commit -m "Set up the knowledge base (hga)"
git -C <dir> push -u origin main      # only if it has a remote
```

For an existing, shared knowledge base, stage only `hga.config.json` (not `-A`), and say before pushing that it
changes the team's settings.

## 4. Machine configuration

Write `~/.claude/hga/config.json` with `{"knowledge_dir": "<dir>"}` if the folder is not the default or the file
does not exist yet. Keep any existing keys: read it first, change only `knowledge_dir`. Overrides of team fields
go here only if the user asks for them.

## 5. Optional, one question each

- **Standing permission for the Slack claim** (only with Slack): show `$INIT/templates/claude-md-snippet.md`
  filled in with the channel, and ask whether to append it to `~/.claude/CLAUDE.md`. It lets `/hga:issue` post
  the claim and the final report in that channel without asking each time; everything else still needs approval.
  Append it only on an explicit yes, and never edit other parts of the file.
- **Triage labels** in repositories the user names: `ready-for-agent`, `ready-for-human`, `needs-info`, and the
  status labels (`in-progress`, `in-review`, without a board). `HGA triage-state` and `HGA status-set` also create
  them on first use, so this is only for seeing them up front: `gh label create <name> --repo <owner/repo>
  --color <hex> --description "<…>"`, skipping existing ones.
- **A first app page:** if the user names an application, create `apps/<app>.md` from the template in
  `apps/README.md` with what you can verify now (repository, default branch, how to run the tests), and a
  `workflow/<app>.md` stub — then validate and commit as in step 6.

## 6. Check

```bash
python3 "$KB/build_map.py" "<dir>"
python3 "$KB/validate_kb.py" "<dir>"
HGA config
HGA doctor
```

All must succeed (warnings allowed). Then summarize in a short table: knowledge base (folder, remote), team
configuration (language, board or labels, Slack or GitHub comments, review provider, limits), machine
configuration, what was skipped and why. End with the next step: "Try `/hga:triage <owner/repo>` or
`/hga:issue <issue URL>`." Mention that `/hga:init` can be re-run to change any of this.
