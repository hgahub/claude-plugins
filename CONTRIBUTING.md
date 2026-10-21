# Contributing

Thanks for helping. Here is how to reach us, and what a change needs to come with.

## Open an issue, not a pull request

Bug reports, ideas and questions go in an [issue](https://github.com/hgahub/claude-plugins/issues). I make the
changes ourselves, so please don't open a pull request unless an issue asked for one. A pull request that no issue
asked for gets closed, however good the change is.

A good bug report names the Claude Code version (`claude --version`), the plugin version, the operating system,
what you ran, what you expected and what happened instead.

## When an issue asked for a pull request

Keep it to one change and link the issue it fixes. Before you open it, run the checks CI runs:

```
python3 scripts/version.py                    # plugin and marketplace versions match
claude plugin validate .
claude plugin validate plugins/hga
claude plugin test plugins/hga                # the panes' tests
python3 -m pytest plugins/hga/tests/py        # the scripts' tests
scripts/plugin-types.sh                       # the plugin's types (.claude-plugin/types, tsconfig.json)
npm run typecheck
```

## Development

```
npm install                                   # TypeScript, for the type check
claude --plugin-dir ./plugins/hga             # load it; this also generates the types
```

Types are generated only by an interactive load (`validate` and `test` do not). `scripts/plugin-types.sh` does
that load in a pseudo-terminal, with its own empty configuration, a placeholder API key and an unreachable API
endpoint: no key and no model call are needed, so CI runs it too. Loading the plugin yourself
(`claude --plugin-dir ./plugins/hga`) generates them as well.

Only one hooks module can be loaded per plugin, so `plugins/hga/hooks/register.tsx` calls the three panes'
`register`. An event without a matcher can be bound only once: the panes' `ui.close` filter on `id`, and the
triage panel's `session.start` uses a `{ cwd: /(?:)/ }` matcher, the intent pane's `{ cwd: /^/ }`, both matching
every session. `isInteractive` is not a usable filter: the desktop app runs in SDK mode, where it is false.

## Releases

Prepare a version PR with `python3 scripts/version.py --set X.Y.Z`, merge it, then push the matching
`vX.Y.Z` tag. The release workflow verifies the version, runs the full CI suite and creates a GitHub Release
with generated notes. See [the release guide](docs/releases.md) for the commands and retry procedure.
