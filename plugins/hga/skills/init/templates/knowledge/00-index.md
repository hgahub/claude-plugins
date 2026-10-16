---
title: "Knowledge base index"
verified_at: "{{DATE}}"
status: verified
review_after_days: 30
managed_by: hga-init
---

# Knowledge base

Shared, file-based notes about our applications, the environments they run in, and what we learned while
working on them. Every claim carries a date and a source: treat it as evidence with a shelf life, not as fact.
The rules are in [policies/source-order.md](policies/source-order.md).

## Quick routes

| Question | Where |
|---|---|
| What is application X, how is it built, run and tested? | [apps/](apps/README.md) |
| Where does it run: hosts, ports, deployments, health checks | [environments/](environments/README.md) |
| What calls what, where the boundaries are | [architecture/](architecture/README.md) |
| What do we know about issue #N, or a topic? | [map/](map/README.md), then [notes/](notes/README.md) |
| How does `/hga:issue` start, test and live-test app X? | [workflow/](workflow/README.md) |
| Known contradictions between sources and measurements | [quality/](quality/README.md) |
| How long did an issue take, how many tokens did it use? | [metrics/](metrics/README.md) (JSON, one per run) |
| Raw input not processed yet | [inbox/](inbox/README.md) |

## How to answer from here

1. Find the page, read its `verified_at` and `status`, and pass both on ("as measured on 2026-09-18…").
2. If someone will act on the answer, check the current state too; if it differs, today's observation wins —
   and fix the page.
3. Mark inferences as inferences. A model's answer is not a source.

## Sources and verification

- Created by `/hga:init` on {{DATE}}.
