---
title: "Source order: which evidence answers which question"
verified_at: "{{DATE}}"
status: verified
review_after_days: 90
managed_by: hga-init
---

# Source order

These do not replace each other:

1. **Running state**: a measurement on the target host is primary, with a timestamp and the command or endpoint.
2. **Behavior**: the source file + the exact Git SHA + whether the checkout had local changes. The local
   checkout, the default branch on GitHub and the deployed build can be three different versions.
3. **Requirements**: the GitHub issue and its project fields. Board status and issue state are separate data.
4. **Secondary notes** (wikis, chat, personal notes): claims waiting for verification until fresh evidence.
5. Mark inferences as inferences. Never turn a model's answer into a fact.

What goes wrong most often:

- **"Done" does not prove deployment.** Neither does a closed issue.
- **HTTP 200 does not prove every backend connection** — readiness and liveness check different dependencies.
- **A model list does not prove a successful inference call.**
- **An empty list after a failed request is not an empty backlog.**

Freshness targets: running environments and active work 1 day, contradictions and decision queues 7 days,
stable architecture 30 days. An expired page is history, not a guarantee of the current state.

**A date means only what was actually checked.** If you re-measured one claim on a page, do not raise the page's
`verified_at`: add a dated section, and say that the other claims' dates are unchanged.

## Sources and verification

- Created by `/hga:init` on {{DATE}} from the plugin's template.
