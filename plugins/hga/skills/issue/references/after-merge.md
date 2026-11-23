# After the merge

Read from `SKILL.md`, "After the merge", when the user says the PR was merged.

1. `gh pr view <pr> --repo <owner/repo> --json state,mergedAt,mergeCommit`: expected `MERGED`. Then `HGA status-set <owner/repo> <n> Done`
   (each issue of the PR; without a board it keeps `labels.in_review`) and `HGA status …`: issue
   `CLOSED (COMPLETED)` + Done. Still open although the PR covered it whole: `gh issue close <n> --repo <owner/repo> --reason
   completed --comment "Done in #<pr> (<merge-sha>)"` and read back. `Ref #<n>` leaves it open. **With
   `labels.closing`:** expected `OPEN` + Done (without a board: `In Review`, the label stays); leave it to the
   maintainer.
2. Delete the remote branch if GitHub did not (`git push origin --delete <branch>`).
3. A dated line in the knowledge note: merge SHA, follow-up issues, the report's link (still no deployment proof).
4. Follow-ups not yet filed: file them now as in 7a, checked on the merged default branch.
