# Verifier Agent Skill

Validate a change's effect on correctness and score. A benchmark result is not trustworthy from a single run in this environment — this session saw run-to-run swings of 300+ points on an *unchanged* commit, and intermittent failures (`CODE=15`, `CODE=32`) that only appeared on the 3rd-6th run of a series that started clean.

## Minimum Checks

- `git status` and commit hash on the app host match what was intended to be deployed.
- Deploy succeeded: all configured services (`isuride-go`, `isuride-matcher`, `isuride-payment_mock`, `mysql` where applicable, `nginx`) report `active`.
- Benchmark **pass/fail** and the **full error map**, not just the score — a passing run with a growing or novel error code is a warning sign even if the score looks fine.
- pprotein artifacts were actually collected for this run (see the Profiler Agent skill for how to tell a stale artifact from a fresh one) and the recorded repo hash matches.

## Run Count Discipline

- For a routine, low-risk change (an index, a query rewrite with no semantic change): 2-3 runs, and do a same-conditions A/B (redeploy the previous commit, remeasure immediately under the same conditions) if the result looks like a regression or looks flat when an improvement was expected — this environment's baseline noise floor drifts over the course of a session (confirmed by re-measuring an unchanged earlier commit and getting a meaningfully different score than its own earlier recorded value).
- For anything matching-adjacent, notification-adjacent, or touching per-tick/per-poll rate limits: **5+ runs minimum** before calling it stable. Both real failures this session (`CODE=15` from a `FOR SHARE` removal, `CODE=32` from the DB split relieving `s1`'s CPU pressure) appeared only on a later run in an initially-clean series, not the first.
- A single catastrophic-looking run (many distinct error categories firing at once, "too many errors" abort) does not need more runs to confirm — that signature reliably indicates a real, reproducible overload; revert immediately and investigate root cause with the Resource Monitor Agent skill before retrying at a smaller scale.

## Resource Verification

When resource evidence matters for the verdict, use the Resource Monitor Agent skill's exact-window Netdata query pattern, not a post-hoc snapshot — decaying load averages queried a minute after a run ends will overstate current load.

## Output Contract

Score before/after, pass/fail, full error map, regression verdict, and — if the change is being accepted despite ambiguous score movement — the specific evidence (A/B result, resource headroom, or query-level timing) that justifies the accept/reject decision beyond a bare score number.
