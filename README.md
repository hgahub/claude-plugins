# claude-plugins

Claude Code plugins by [hgahub](https://github.com/hgahub), in one plugin marketplace (`hga-plugins`).

> The panes use Claude Code's mod API, which is in early access and may change between releases. Written and
> tested with Claude Code 2.1.289.

## Install

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Then run [`/hga:init`](plugins/hga/skills/init/SKILL.md) in Claude Code. Update with `claude plugin update hga@hga-plugins`, then `/reload-plugins`
(or a new session).

## Plugins

### hga

Takes GitHub issues from intent and triage to a reviewed pull request, with a shared, evidence-based knowledge base.

The groups below describe each skill's primary role. All seven skills can be invoked by either the user or
Claude; the grouping does not restrict invocation.

#### User-invoked

Entry points for setting up the plugin, starting work and inspecting results.

- [`/hga:init`](plugins/hga/skills/init/SKILL.md) — checks prerequisites and sets up the knowledge base,
  team and machine configuration;
- [`/hga:intent`](plugins/hga/skills/intent/SKILL.md) — turns a few sentences into an intent.md through
  interviewing and research, with a readiness gate;
- [`/hga:triage`](plugins/hga/skills/triage/SKILL.md) — vets and prepares issues, picks the next one and
  launches a parallel implementation session;
- [`/hga:issue`](plugins/hga/skills/issue/SKILL.md) — takes an issue through implementation, tests, PR,
  review, cleanup and a measured report; also launched by triage;
- [`/hga:dashboard`](plugins/hga/skills/dashboard/SKILL.md) — creates or refreshes a dashboard of issue
  run metrics, including lead time, tokens, estimated API cost and review rounds.

#### Model-invoked

Helpers Claude can use within a workflow. You can also invoke either command directly.

- [`/hga:new-issue`](plugins/hga/skills/new-issue/SKILL.md) — turns an approved intent into a GitHub issue
  and puts it on the board, as part of the intent workflow or on its own;
- [`/hga:knowledge`](plugins/hga/skills/knowledge/SKILL.md) — reads and writes the shared knowledge base,
  with dates and sources, whenever context or verified findings need to be kept.

#### Panes

Commands that toggle live views of the workflows.

- [`/intent-pane`](plugins/hga/README.md#intent-pane-and-progress-band) — the intent's stations and coverage;
- [`/issue-pane`](plugins/hga/README.md#issue-pane) — the running issue's steps;
- [`/triage-pane`](plugins/hga/README.md#triage-panel) — the repository's triage dashboard.

The progress band above the prompt appears automatically while an intent is running.

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

## Releases

Prepare a version PR with `python3 scripts/version.py --set X.Y.Z`, merge it, then push the matching
`vX.Y.Z` tag. The release workflow verifies the version, runs the full CI suite and creates a GitHub Release
with generated notes. See [the release guide](docs/releases.md) for the commands and retry procedure.

## License

[MIT](LICENSE)
