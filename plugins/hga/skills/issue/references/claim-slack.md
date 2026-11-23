# Step 1 — the claim with Slack

Read from `SKILL.md`, step 1, when `slack` is not `null`. The check (`HGA claim-check`) and the run marker stay
in step 1.

**With Slack:**

1. `slack_read_channel` on `slack.channel_id` with `oldest` = `HGA midnight`. Someone else claimed it today →
   tell the user and stop.
2. Post one line:
   ```
   <your name or agent name> · <repo> · #142 https://github.com/acme/web-app/issues/142 · fix · session <tag>
   ```
   Verb: `implement` / `fix` / `verify` / `re-verify` (a verification adds the head SHA). Each issue in the same
   PR gets its own line.
3. Read back with `oldest` = `Read back from`. Of the claims on the same issue, the smallest `ts` wins. If it is
   not yours, reply in your thread `withdrawn — earlier claim: <link>`, tell the user and stop.
4. The `message_ts` is the thread for every further message.
