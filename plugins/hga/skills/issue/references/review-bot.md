# Step 8 — the bot review

Read from `SKILL.md`, step 8, when `review.provider` is not `local` and the track is standard or high (not
quick). Points 2 and 3 of step 8; the other points stay there.

2. **Bot** (standard and high, not quick): `HGA review-request <owner/repo> <pr>`, ~20 s after a push (too early fails with
   "ref does not exist"). Then in the background: `HGA review-wait <owner/repo> <pr> --issue <n> --timeout-min 30`
   — exit 0 = 👍, 1 = findings (`severity · path:line · id · title`), 2 = timeout, 3 = the review failed. Only a
   bot review of the exact head commit counts; a clean one is recorded for step 8's machine check. Copilot and Greptile support is newer; if the output looks wrong, check the API
   and say so in the report.
3. **Findings** (`gh api repos/<o>/<r>/pulls/<pr>/comments`): fix real ones, and **before the next round fix the
   siblings** (same bug in other consumers, same pattern elsewhere). Gate, commit `fix(#n): …`, push, reply to
   every comment (`…/comments/<id>/replies`: what was fixed in which commit, or why not), request again.
