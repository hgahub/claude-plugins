# environments/

One page per host, cluster or environment (`staging.md`, `prod-eu.md`): what runs there, ports, containers or
services, how deployments happen, which health checks are safe to call. Read-only checks only — no restarts,
deploys or load tests to refresh a page.

Same frontmatter as every page; give running state a short `review_after_days` (1–7).
