---
name: dashboard
description: Use when someone wants to see how the hga issue runs went — lead times, elapsed time per section, tokens, an API-price cost estimate, review rounds, risk classes, aborted runs, plan usage — across repositories and over a period. Aggregates the knowledge base's metrics records (written by /hga:issue step 12) with `hga_issue.py metrics`, then creates a claude.ai Dashboard artifact on first use or refreshes the existing one with the new rows. Triggers include "hga dashboard", "metrics dashboard", "how fast do we solve issues", "how many tokens did the issues take", "refresh the dashboard", "show the issue metrics".
user-invocable: true
argument-hint: "[refresh]"
---

# Metrics dashboard

A colorful, interactive dashboard on claude.ai over the `/hga:issue` runs, filterable by repository and period.
The knowledge base is local (or a git repository), so the dashboard holds a **snapshot**: the rows are an
attached file, refreshed by running this skill again. One dashboard per user: its link is in the machine
configuration.

- `HGA` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/issue/scripts/hga_issue.py"` (`python` on Windows). Spell it
  out in every Bash call — a shell variable does not split in zsh.
- `K` = `knowledge_dir` from `HGA config` (default `~/.hga/knowledge`). From the same output: `language` (the
  dashboard's words: title, headings, labels, notes — column names and model ids stay as they are), and
  `dashboard_url` (the existing dashboard, if any; it lives in `~/.claude/hga/config.json`).
- `F` = `<scratchpad>/hga-metrics.csv` (this session's scratchpad directory; never inside the knowledge base or
  a repository).

`/hga:dashboard` creates the dashboard if there is none, otherwise refreshes it. `/hga:dashboard refresh` only
refreshes the data, and stops with a note if there is no dashboard yet. A request to change the page ("add a
chart of …") is a refresh plus that change.

## 1. Preconditions

- The `Artifact` tool must offer the **Dashboard** type: `Artifact` `action: "list"`, `scope: "types"`,
  `type_query: "dashboard"`. Without it (no claude.ai Artifacts in this session), say so and stop; the rows
  can still be had as a file: `HGA metrics --cost --format csv`.
- If `K` has a remote, pull first (`git -C "$K" pull --ff-only --quiet`): every team member's runs land there.
  If `K` does not exist, say so and suggest `/hga:init`.

## 2. Aggregate

```bash
HGA metrics --cost --format csv > "$F"
```

All repositories and all dates: the dashboard filters them itself. Show the stderr lines to the user (skipped
records, models without a price, the cost note, the outcome counts with the abort rate). Count the `kind=run`
rows: with none, there is nothing to show yet — say that `/hga:issue` writes a run marker once its claim holds
and the record at the end of step 12, and stop. The file is a few hundred
bytes per run; above 8 MB (the type's limit) say so and narrow it with `--since`.

The rows (one table, the `kind` column tells them apart; the schema of the records behind them is in
`$K/metrics/README.md`):

| `kind` | One row per | Filled columns |
|---|---|---|
| `run` | run of `/hga:issue` | `run`, `repo`, `issue`, `verb`, `date` (start date), `started_at`, `ended_at`, `finished`, `outcome`, `difficulty`, `review_rounds`, `risk` (low / standard / high, empty in older records), `na_steps` (steps reported not_applicable); `wall_s`, `active_s`, `review_wait_s`, `pause_s`, `lead_s`; `calls`, the four token fields, `total_tokens`; `five_hour_start_at/_pct`, `five_hour_end_at/_pct`; `api_cost_usd_est` |
| `section` | run and section (`section`: Prepare, Build, Review, Finish; `section_index` 0–3) | the run's identity columns, elapsed (`lead_s` included), tokens, `api_cost_usd_est` |
| `model` | run, section and model (`model`: the model id) | the run's identity columns, `section`, tokens, `api_cost_usd_est` |

- The sections partition a run: their `wall_s`, tokens and cost add up to the run's. Model rows add up to
  their section's tokens. Never add run rows to section rows.
- `lead_s` = `wall_s` − `pause_s` (an empty `pause_s` counts as 0; an empty `wall_s` leaves it empty): the lead
  time without pauses — a machine that was off overnight shows as a pause, not as work. Pauses are measured per
  section too, so the sections' `lead_s` need not add up to the run's.
- `api_cost_usd_est` is the tokens at Anthropic **API list prices** (a table in `hga_issue.py`): an estimate,
  **not** what the Claude subscription costs. Wherever it shows (tile, axis, tooltip, legend), its label says
  so.
- `five_hour_*` is the **account's** five-hour plan usage at the run's start and end: every session of the
  account moves it, parallel ones included. Show it as context for the period, never summed or attributed to
  an issue.
- A run without a transcript has empty token and cost cells, and only `wall_s` (its `lead_s` equals it); a run
  without step times has all its time in Prepare. Empty cells are gaps, not zeros.
- `outcome` (on every row of the run): `finished` / `unfinished` — the run wrote its record (step 12 `done` or
  not); `aborted` — only its start marker exists, 24 hours after the start (`--stale-hours`): the run never
  reached the report; `open` — only the marker, younger than that: it may still be going on; **empty** — a
  record from before the markers existed, which never had one. An `aborted` or `open` run has a run row only:
  no times, tokens or sections.
- **Abort rate** = `aborted` / (`finished` + `unfinished` + `aborted`). `open` runs and runs with an empty
  `outcome` are left out of both sides: an older run could not have been counted as aborted.

## 3. Say who can read it

Before every upload, say: everyone who can open the dashboard can read the attached file — repository names,
issue numbers, times, token counts and the cost estimate; the dashboard is private until the user shares it.
On the **first** upload (creating), ask with `AskUserQuestion` — "Upload the metrics file (Recommended)" /
"Not now" — and stop on "Not now". On a refresh, the sentence is enough.

## 4. Create (no `dashboard_url`, or the old one is gone)

If `dashboard_url` is set, `Artifact` `action: "read"` on it first; if it is gone or the read says the user is
not a writer, say so and ask whether to make a new one (the old link is then replaced).

1. `Artifact` publish with the Dashboard type's `type_url`, `title` = "hga metrics" in the configured
   language, `auto_open: "after_first_write"`, no files. The result carries the dashboard's `url` and the
   type's own instructions: **follow them** for everything about the store (documents, datasets, marking,
   `dash.*`, the check). Read the references they name before writing: `artifact-type/reference/features.md`
   (filters) and `artifact-type/reference/design-defaults.md`.
2. Right away, write the `url` into `~/.claude/hga/config.json` as `dashboard_url`: read the file first and
   change only that key (keep `knowledge_dir` and the rest). `HGA config` must then print it.
3. Upload `F` to the dashboard's asset store (`Artifact` publish, `url`, `file_path` = `F`, `asset: true`);
   keep the `url` the reply gives (`/_blob/<id>`) as it is.
4. Write the store in one `ArtifactData` `batch`:
   - `dash/meta` — `{title}`.
   - `datasets/hga_metrics` — `title` "hga runs, sections, models" (in the language), a `description` saying
     what one row is and that the cost column is an API-price estimate, `source: {kind: "file", url, name:
     "hga-metrics.csv"}`, `updated: {at: <HGA now>, by: "hga /hga:dashboard"}`. No `schedule` and not
     `fixed`: this skill refreshes it.
   - `dash/params` — the two filters and the pause mode (section 6), as `features.md` describes them.
   - `files/index.html` — the page (section 6).
5. Run the type's check as its instructions say, fix what it confirms, then hand over (section 7).

## 5. Refresh (`dashboard_url` set)

1. `Artifact` `action: "read"` on `dashboard_url`, then `ArtifactData` `get` `datasets/hga_metrics`. If either
   fails, go to section 4.
2. Upload the new `F` (as in 4.3), then one `ArtifactData` `update` of `datasets/hga_metrics`: the source's new
   `url` and `name`, and `updated` (`at` = `HGA now`). Get it back and check the `url`.
3. The previous file is an asset this skill uploaded and nothing references any more: remove it
   (`Artifact` `action: "delete"`, `url` = the dashboard, `path` = its asset id from the old `/_blob/<id>`).
4. Leave the page alone, unless the user asked for a change or it lacks a chart or a behavior from section 6
   (such as the pause toggle; an older version of this skill wrote it): then `get` `files/index.html` (and
   `dash/params` if a filter is missing), change only that, and run the type's check.

## 6. The page

Follow the Dashboard type's instructions for the page's structure, colors and layout; d3 v7 as the global `d3`,
everything drawn inside `dash.onData` from `dash.data("hga_metrics")`. The CSV's cells arrive as text:
`Number()` the numbers (an empty cell is `null`, not 0), `"true"` is finished. One color per section and per
model, the same in every chart; each chart gets an `id`, a heading and a tooltip. Durations as `1 h 25 min` /
`40 min`, tokens as `1.2M` / `350K`, cost as `$12.40`. Size every horizontal axis's right margin from its last
tick label (`getComputedTextLength()` after drawing, then redraw) — a cut label fails the type's check
(`labels_cut`).

**Filters** (in `dash/params`, applied to every chart and tile): **repository** — "All" or one `repo` from
the data; **period** — on `date` (the run's start): last 7 / 30 / 90 days, this month, all, or a from–to
range; **pauses** — `exclude` (the default) or `include`. A calc or chart that reads the rows filters them by
repository and period.

**Lead time** is `lead_s` (without pauses) when `pauses` is `exclude`, `wall_s` when it is `include` —
everywhere it shows below: one calc (`lead`) picks the column, and every chart, tile and table reads it from
there, never `wall_s` directly. Every lead-time tooltip shows the lead time without pauses, the pauses
(`pause_s`) and the full wall time (`wall_s`), whichever mode is on.

From top to bottom:

1. **Tiles** (each a `dash.calc` over the filtered `kind=run` rows): runs, finished runs, **abort rate** (as
   defined in section 2, with "n of m runs" under it, and "no runs with a marker" instead of 0 % when m is 0),
   median lead time (with "without pauses" or "with pauses" under it, after the mode), median active time,
   total tokens, `api_cost_usd_est` total — labeled "API-price estimate (not the subscription cost)" — and
   median review rounds. The lead-time, time and token
   figures come from runs with a record (`outcome` not `aborted` / `open`).
2. **Lead time per issue** — one bar per run (`repo#issue`, by start), length the lead time, colored by
   `difficulty` (easy / medium / hard / not reported), with `active_s` as a thinner bar inside it; the tooltip
   adds review wait, pauses, verb and review rounds.
3. **Solving speed** — per week of `date`: finished runs (bars), aborted runs (a second, muted bar beside
   them), and the median lead time (line), so the trend shows whether issues get done faster and fewer runs
   die on the way.
4. **Elapsed by section** — one stacked bar per run from the `kind=section` rows, Prepare → Build → Review →
   Finish, in each section's lead time (its own `lead_s` or `wall_s`, after the mode); a toggle to show the
   shares (100 %) instead.
5. **Tokens and estimated cost by section and model** — from the `kind=model` rows over the filtered period:
   one stacked bar per section, stacked by model, with a toggle between tokens (`total_tokens`, or split into
   input / output / cache write / cache read) and `api_cost_usd_est`. The cost view's axis title says "API-price
   estimate, USD".
6. **Review rounds** — how many runs needed 0, 1, 2, … rounds (a histogram over `review_rounds`), and next to
   it rounds against lead time (one dot per run).
7. **By risk class** — the filtered `kind=run` rows with a record, grouped by `risk` (low → standard → high, then
   "not classified" for an empty cell: older records, or a run where `HGA risk` never ran), one color per class,
   the same wherever the class shows. Per class: the number of runs, the median lead time and active
   time (`active_s`) as paired bars, the median and the spread of `review_rounds`, and the average `na_steps`
   (the gates the class made not applicable). The subtitle says that the class comes from the changed files
   (`HGA risk`), so it shows whether low-risk runs really are cheaper and high-risk ones get more review. A
   class with fewer than 3 runs is shown, but its bars are marked "few runs".
8. **Five-hour plan usage (account)** — on a time axis, one segment per run from
   `five_hour_start_at`/`_pct` to `five_hour_end_at`/`_pct`, colored by repository; the subtitle says it is the
   whole account's usage (all sessions, parallel ones included), context for the period, not the issue's cost.
   Runs without both snapshots are left out, and the chart says how many.
9. **Runs** — a table of the filtered `kind=run` rows (run, repo, issue, start, outcome, lead time, pauses,
   active, difficulty, risk, n/a steps, rounds, tokens, cost estimate), newest first, keyed on `run`; aborted runs stand
   out.

A filter that leaves no rows shows "No runs in this period" in each chart, not an empty axis.

## 7. Hand over

In the configured language, briefly: the link; what it shows (how many runs, repositories, period, the abort
rate and since when markers exist); that the
cost is an estimate at API list prices, not the subscription's cost, and the five-hour usage is account-wide
context; that it is a snapshot as of now, refreshed by `/hga:dashboard refresh` (after new `/hga:issue` runs);
and that it is private until shared, and whoever can open it can read the attached rows. On a refresh: the
number of runs before and after.
