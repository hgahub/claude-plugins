# claude-plugins

Claude Code plugins by [hgahub](https://github.com/hgahub), in one plugin marketplace (`hga-plugins`).

> The panes use Claude Code's mod API, which is in early access and may change between releases. Written and
> tested with Claude Code 2.1.289.

## Install

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Then run `/hga:init` in Claude Code. Update with `claude plugin update hga@hga-plugins`, then `/reload-plugins`
(or a new session).

## Plugins

### hga

Takes GitHub issues from triage to a reviewed pull request, with a shared, evidence-based knowledge base:

- `/hga:init` — prerequisites, knowledge base (new or the team's), team and machine configuration;
- `/hga:intent` — turns a few sentences into an intent.md in the knowledge base, by interviewing and research,
  with a readiness gate;
- `/hga:new-issue` — makes a GitHub issue from the intent, and puts it on the board;
- `/hga:triage` — vets an issue, finalizes it into an implementable brief, picks the next one, launches a
  parallel implementation session as its subtask;
- `/hga:issue` — claim, In Progress, worktree, tests, live browser test, PR, review (local, Codex, Copilot or
  Greptile), Done, cleanup, knowledge base and a measured report, on a verified checklist;
- `/hga:knowledge` — reads and writes the knowledge base, with dates and sources;
- three live panes: `/intent-pane` (the intent's stations and coverage), `/issue-pane` (the running issue's
  steps) and `/triage-pane` (the repository's dashboard), and a progress band above the prompt
  (Intent → Issue → Triage → Build).

GitHub is required; Slack, a GitHub project board and a review bot are optional. Details:
[plugins/hga/README.md](plugins/hga/README.md).

## Development

```
npm install                                   # TypeScript, for the type check
claude plugin validate plugins/hga
claude plugin test plugins/hga                # the panes' tests
python3 -m pytest plugins/hga/tests/py        # the scripts' tests
scripts/plugin-types.sh                       # the plugin's types (.claude-plugin/types, tsconfig.json)
npm run typecheck
```

Types are generated only by an interactive load (`validate` and `test` do not). `scripts/plugin-types.sh` does
that load in a pseudo-terminal, with its own empty configuration, a placeholder API key and an unreachable API
endpoint: no key and no model call are needed, so CI runs it too. Loading the plugin yourself
(`claude --plugin-dir ./plugins/hga`) generates them as well.

## License

[MIT](LICENSE)
