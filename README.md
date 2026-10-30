# claude-plugins

Claude Code plugins by [hgahub](https://github.com/hgahub), in one plugin marketplace (`hga-plugins`).

> The panes use Claude Code's mod API, which is in early access and may change between releases. Written and
> tested with Claude Code 2.1.289.

## Install

```
claude plugin marketplace add hgahub/claude-plugins
claude plugin install hga@hga-plugins
```

Then run [`/hga:init quick`](plugins/hga/skills/init/SKILL.md) in Claude Code: a local knowledge base with the
defaults (status labels, GitHub comments, local review), after at most two questions. `/hga:init` changes any of
it later and offers the choices `quick` skipped. Update with `claude plugin update hga@hga-plugins`, then
`/reload-plugins` (or a new session).

New here? The [quickstart](docs/quickstart.md) takes you from this install to a reviewed pull request in a
repository of your own.

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

## Contributing

Open an issue rather than a pull request. Development, checks and releases: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
