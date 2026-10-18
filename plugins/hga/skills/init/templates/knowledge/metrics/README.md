# metrics/

One JSON record per run of `/hga:issue`: how long it took, how many tokens it used and where, written by
`hga_issue.py metrics-record` at the end of step 12 and committed on its own. Earlier, once the run's claim
holds (step 1), `hga_issue.py metrics-start` writes a **run marker** to the same file; the record overwrites it.
A marker that is never overwritten is a run that did not reach the report. Machine data for aggregation
per repository and period (`hga_issue.py metrics` flattens them into rows, `/hga:dashboard` charts them), not
pages: the validator checks that each record is a JSON object with an integer `schema` and holds nothing that
looks like a secret; the map does not list them. Do not edit them by hand.

File: `metrics/<owner>/<repo>/<issue>-<start, UTC, YYYYMMDDTHHMMSSZ>.json` (e.g.
`metrics/acme/web-app/142-20261013T065305Z.json`), owner and repo in lower case. Every run of an issue has its
own start, so re-runs never overwrite each other, and parallel sessions never write the same file; recording
the same run again rewrites its file.

## Schema 1

Times are ISO 8601 with the configured time zone's offset; durations are whole seconds; tokens are the API's
own `usage` field names.

| Field | Meaning |
|---|---|
| `schema` | `1`. A reader skips records with a schema it does not know. |
| `stage` | `started` — a run marker (below); `recorded` — the record. Absent in records written before the markers existed: those are records. |
| `repo`, `issue`, `verb` | `owner/repo` as given, the issue number, the claim verb (`fix`, `implement`, …). |
| `started_at`, `ended_at` | The run's start (step 0's `HGA now`) and end (step 12's first `done`, or `--until`). |
| `finished` | Whether step 12 was `done` when the record was written. |
| `recorded_at` | When the record was written. |
| `sessions`, `transcripts` | The Claude Code session ids measured; how many main and subagent transcripts were found. |
| `difficulty` | `easy` / `medium` / `hard` as reported in step 12, or `null`. |
| `review_rounds` | The review's rounds (bot rounds, or local review rounds), or `null`. |
| `risk` | The change's risk class from `hga_issue.py risk` (`low`, `standard`, `high`), or `null`. Absent in older records. |
| `elapsed` | `wall_s`, `active_s`, `review_wait_s` (idle while `review-wait` ran), `review_wait_runs`, `pause_s`, `pauses` (`from`, `to`, `seconds`, `reason`). Without a transcript only `wall_s` is set, the rest is `null`. |
| `tokens` | The run's total: `calls`, `output_tokens`, `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`; subagents included, each API response once. `null` without a transcript. |
| `models` | The same token fields per model id (`claude-opus-5-5`, …): the basis for a cost estimate. |
| `sections` | The checklist's four sections: `title` (Prepare, Build, Review, Finish), `steps` (`[from, to]`), `from`, `to`, and `elapsed`, `tokens`, `models` within that window. |
| `steps` | All 13 steps: `step`, `name`, `state` (`done`, `skipped`, `not_applicable` — the gate does not apply to the risk class —, `in_progress` or `null`), `started_at`, `ended_at` (`null` if unknown). |
| `five_hour` | `scope: "account"`, `start` and `end`: `{at, percent_used}` of the plan's five-hour limit at step 0's start and at step 12's `done`, or `null`. |

**Sections** split the run into contiguous windows: a section starts at the earliest start (or end) of its
steps and lasts until the next section starts, so the sections' `wall_s` and tokens add up to the run's.
Active time and pauses are measured within each window: a pause cut in two by a section boundary can fall
under the pause threshold on both sides, so per section they need not add up to the run's. Work that returns
to an earlier step (a fix during the review) counts in the section running at the time. A section whose steps
have no times (records from before the pane kept step times) gets an empty window.

**Run markers.** A marker is a schema-1 record with `stage: "started"` and only `schema`, `stage`, `repo`,
`issue`, `verb`, `started_at`, `ended_at` (`null`), `finished` (`false`), `recorded_at` and `sessions`; every
other field is absent. A reader that does not know `stage` sees an unfinished run without times. `hga_issue.py
metrics` derives each run's `outcome`: `finished` / `unfinished` for a record (with `stage`), `aborted` for a
marker older than 24 hours (`--stale-hours`), `open` for a younger one, and none for a record without `stage`
(it never had a marker, so it does not count in the abort rate). A marker of the same issue sharing a session
with a record is the same run, and is not counted again.

**Five-hour usage is account-wide.** Every session of the account moves it, parallel ones included, so the
difference between `start` and `end` is context for the period, never the issue's own cost. The issue's cost
is in `tokens` and `models`.
