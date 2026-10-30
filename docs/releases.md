# Releases

The `hga` plugin uses stable `X.Y.Z` versions and matching `vX.Y.Z` Git tags.
Its version must agree in `plugins/hga/.claude-plugin/plugin.json` and the `hga` entry of
`.claude-plugin/marketplace.json`. The root npm package is private build tooling, not a published package.

## Prepare a version PR

1. Start a branch or worktree from the current `origin/main`.
2. Choose a higher version: patch for fixes, minor for compatible features, major for breaking changes.
   While below 1.0, use a minor increment for breaking changes and call them out in the PR.
3. Run `python3 scripts/version.py --set X.Y.Z` with the chosen version. This updates both manifests;
   it does not commit, tag or push. Review both changes and describe the release's user-visible changes
   and any migration steps in the PR.
4. Re-check the [compatibility table](../plugins/hga/README.md#compatibility) with the current Claude Code:
   update the cells you measured, its "Checked on" line, and the Claude Code version in both mod-API notes
   (`README.md`, `plugins/hga/README.md`). A cell nobody measured stays "not tested".
5. Commit, push and open a PR. Wait for CI, then merge. Do not tag the feature branch: squash and rebase
   merges can change its commit SHA.

Use `python3 scripts/version.py` to check consistency without modifying files. CI runs this check alongside
the existing Python tests. Stable versions only are supported; prerelease and build suffixes are rejected.

## Publish the merged version

From a clean checkout, replace `X.Y.Z` with the merged version and run:

```sh
git fetch origin main --tags
git switch --detach origin/main
python3 scripts/version.py --tag vX.Y.Z
git tag -a vX.Y.Z -m 'Release vX.Y.Z'
git push origin refs/tags/vX.Y.Z
```

The tag push is the publication decision. `.github/workflows/release.yml` then:

1. Requires the tagged commit to be in `origin/main` and the tag to match both manifests.
2. Calls the full existing CI workflow at the tagged revision: Python tests on Linux, macOS and Windows,
   plugin validation, pane tests and the TypeScript check. The documentation path exclusions do not apply
   to this reusable-workflow call.
3. Creates a GitHub Release with generated notes from merged PRs and GitHub's source archives, after all
   checks pass. Write access is limited to this final job; the built-in `GITHUB_TOKEN` is sufficient.
4. Moves the `stable` branch to the tagged commit, creating it on the first release. It only fast-forwards:
   a tag older than `stable` leaves it unchanged.

Check the **Release** run in Actions, the resulting release on GitHub, and that `stable` points at the tag
(`git ls-remote origin stable`). No npm credentials or npm publish step are needed. No tag, release or `stable`
move is created merely by merging the workflow or the version PR.

## What an update installs

Users add the marketplace at the `stable` branch (`claude plugin marketplace add hgahub/claude-plugins#stable`),
so `claude plugin update hga@hga-plugins` installs the latest release, never an unreleased commit. `main` is the
development line. An update brings a new copy only when the plugin's `version` changes, which each release does.

An installation added without `#stable` follows `main`. Adding the marketplace again does not change its source,
so move it once; removing the marketplace uninstalls the plugin, but hga keeps its configuration and knowledge
base outside the plugin (`~/.claude/hga/`, the knowledge base folder), and both stay:

```sh
claude plugin marketplace remove hga-plugins
claude plugin marketplace add hgahub/claude-plugins#stable
claude plugin install hga@hga-plugins
```

## Retry and corrections

For a transient runner or publication failure, rerun the failed jobs in the same Actions run. An existing
release is left unchanged, and a tag moved or removed while CI ran prevents publication. Never force-move
a published version tag. For a code, manifest or workflow defect, fix it in a PR, choose a higher version,
merge and push a new tag. If the `stable` step failed after the release was created, rerunning the job moves it;
never push to `stable` by hand.
