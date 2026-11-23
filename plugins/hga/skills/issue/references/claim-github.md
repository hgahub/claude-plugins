# Step 1 — the claim without Slack

Read from `SKILL.md`, step 1, when `slack` is `null`. The check (`HGA claim-check`) and the run marker stay in
step 1.

**Without Slack:**

1. `gh issue edit <n> --repo <owner/repo> --add-assignee @me`, then the comment
   `Claimed · fix · <your name or agent name> · session <tag>`.
2. Read back: `HGA claim-check <owner/repo> <n> --verb <verb> --since <Read back from>`. Exit 0 (`first`): go on.
   Exit 5 (`later`): edit your comment (id on the `Your claim:` line) to
   `Withdrawn · fix · <name> · session <tag> — earlier claim: <url>` via `gh api -X PATCH
   repos/<owner>/<repo>/issues/comments/<id>`, remove your assignment only if the winner is another account,
   tell the user and stop. Exit 4: your comment is missing — post it and read back again.
