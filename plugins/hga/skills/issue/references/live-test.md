# Step 6 — the live user test

Read from `SKILL.md`, step 6, when the class is not `low`. `${CLAUDE_SKILL_DIR}` is not substituted in this file:
it is the skill's folder, the one above `references/`.

**High class:** wherever this section allows a skip, ask the maintainer instead.

1. **Start** with `preview_start`, using a temporary entry in the session folder's `.claude/launch.json` (note
   whether the file and folder existed: step 10 restores exactly that) and the command from the workflow page, on
   a separate port. For Python apps the helper runs the worktree's code with the main checkout's `.env`:
   ```json
   {
     "name": "<app>-<n>-live",
     "runtimeExecutable": "uv",
     "runtimeArgs": ["run", "--project", "<REPOS>/<repo>-<n>", "python",
       "${CLAUDE_SKILL_DIR}/scripts/run_worktree.py",
       "--main", "<REPOS>/<repo>", "--worktree", "<REPOS>/<repo>-<n>", "--port", "<port>",
       "--env", "<KEY>=<value>", "--abs-env", "<keys holding relative paths>"],
     "port": <port>
   }
   ```
   **The server must run the worktree's code:** `preview_start` runs in the main checkout, so a plain
   `npm run dev` silently serves the unfixed code. Point the command at the worktree, and make the first live
   evidence prove it (an import path in the log, or a response the fix changed).

   **If `preview_start` is declined:** in an interactive session a person declined — ask (Bash start, they start
   it, or skip). In an unattended run (scheduled, or launched by the triage) the app declined by itself — start the
   same command with Bash in the background, wait for the port, and use the process output as the server log. Skip
   only if both paths fail, with both errors as evidence.
2. **Browser:** `live_test.browser` first, the other if it is not in the session — equal, no ⚠️ for falling
   back. Follow the issue's **"What we measured"** steps in the UI.
3. **Evidence:** state via `javascript_tool` (the workflow page lists the state objects), the server log, and
   screenshots. Read transient UI (toasts) from the DOM. In Chrome a JS evaluation times out at 45 s: wait ≤40 s
   per call.
4. **Afterwards:** note console errors caused by the changed code; stop the server, close the tab, confirm the
   port no longer listens.
5. **On failure, back to step 5** (pane: step 5 `in_progress` again): regression test if automatable, fix, gate,
   commit, and repeat the live test **from the beginning**. At most 3 rounds, then ask the maintainer before the PR.
6. **Verdict** by the "Acceptance criteria": **`PASSED`** (every UI-checkable criterion holds, no new console
   error), **`FAILED`** (still failing after round 3), **`NOT VERIFIED`** (the app did not start). Below it, one
   line per criterion: `C<i> ✅ / ❌ — what you did, what you saw`; non-UI criteria are `—`. Only `PASSED` can be
   `done` on the pane (`PASSED · Chrome · C1–C4 ✅`); the others are `skipped`. The verdict leads the PR's "Live
   user test" section and is in the report.
