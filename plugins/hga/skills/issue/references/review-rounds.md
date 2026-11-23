# Step 8 — the round limit and closing the review

Read from `SKILL.md`, step 8, when a review round ended with findings and the class's review is not a single
round (low, quick). Points 4 and 5 of step 8; the other points stay there.

4. **Round limit — closing is the maintainer's decision.** Ask with `AskUserQuestion` before the next fixes when
   `review-wait` reports round `review.ask_after_rounds` (default 5), or from round 3 a round finds only minor
   findings in earlier rounds' fixes. Give rounds, findings per round, severities, and since when they stopped
   shrinking. Options: "Close with a follow-up issue (Recommended)", "Fix this round, then close", "Continue until
   👍". (A PR that changes a test suite or measuring tool is the exception — its rounds can surface real bugs; say
   so.)
5. **Closing, if decided:** open findings into a follow-up issue (7a), each comment answered with its link; still
   fix severe findings and regressions, noting that no bot reviewed that fix; fill in the PR's "Review"; take
   round counts from `review-wait` or the API, not memory.
