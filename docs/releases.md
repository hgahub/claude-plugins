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
4. Commit, push and open a PR. Wait for CI, then merge. Do not tag the feature branch: squash and rebase
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

Check the **Release** run in Actions and the resulting release on GitHub. No npm credentials or npm publish
step are needed. No tag or release is created merely by merging the workflow or the version PR.

## Retry and corrections

For a transient runner or publication failure, rerun the failed jobs in the same Actions run. An existing
release is left unchanged, and a tag moved or removed while CI ran prevents publication. Never force-move
a published version tag. For a code, manifest or workflow defect, fix it in a PR, choose a higher version,
merge and push a new tag.

The GitHub Release is a tested source snapshot and changelog. The current marketplace installation tracks
the Git repository's default branch; this workflow does not turn plugin updates into release-only delivery.
Users continue to update with `claude plugin update hga@hga-plugins` and `/reload-plugins`.
