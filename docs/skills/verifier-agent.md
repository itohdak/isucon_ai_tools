# Verifier Agent Skill

Validate a change's effect on correctness and score. A benchmark result is not trustworthy from a single run in this environment — this session saw run-to-run swings of 300+ points on an *unchanged* commit, and intermittent failures (`CODE=15`, `CODE=32`) that only appeared on the 3rd-6th run of a series that started clean.

## Minimum Checks

- `git status` and commit hash on the app host match what was intended to be deployed.
- Deploy succeeded: all configured services (`isuride-go`, `isuride-matcher`, `isuride-payment_mock`, `mysql` where applicable, `nginx`) report `active`.
- Benchmark **pass/fail** and the **full error map**, not just the score — a passing run with a growing or novel error code is a warning sign even if the score looks fine.
- pprotein artifacts were actually collected for this run (see the Profiler Agent skill for how to tell a stale artifact from a fresh one) and the recorded repo hash matches.

## Run Count Discipline

**This guidance assumes a practice environment with an automated, freely-repeatable benchmark command (`sudo -u isucon ./bench run ...`).** A real ISUCON contest benchmark is normally triggered manually through a portal website, not scripted, and is commonly rate-limited (e.g. a cooldown between runs and/or a cap on total runs) — you cannot assume 3-5+ runs per change are affordable there. Treat everything below as the practice-environment ideal, and see "Contest-Mode Adjustment" for what to do when runs are actually scarce.

- For a routine, low-risk change (an index, a query rewrite with no semantic change): 2-3 runs, and do a same-conditions A/B (redeploy the previous commit, remeasure immediately under the same conditions) if the result looks like a regression or looks flat when an improvement was expected — this environment's baseline noise floor drifts over the course of a session (confirmed by re-measuring an unchanged earlier commit and getting a meaningfully different score than its own earlier recorded value).
- For anything matching-adjacent, notification-adjacent, or touching per-tick/per-poll rate limits: **5+ runs minimum** before calling it stable. Both real failures this session (`CODE=15` from a `FOR SHARE` removal, `CODE=32` from the DB split relieving `s1`'s CPU pressure) appeared only on a later run in an initially-clean series, not the first.
- A single catastrophic-looking run (many distinct error categories firing at once, "too many errors" abort) does not need more runs to confirm — that signature reliably indicates a real, reproducible overload; revert immediately and investigate root cause with the Resource Monitor Agent skill before retrying at a smaller scale.

### Contest-Mode Adjustment (scarce/rate-limited benchmark runs)

When the benchmark can only be triggered manually via a portal and each run has a real cost (rate-limit cooldown, a cap on total attempts, or simply less available time than a practice session), do not default to the run counts above. Instead:

- **Build confidence before spending a run**, not after. Use Netdata resource snapshots, `EXPLAIN`/`slp` query-level analysis, code review, and the App Understanding Agent's risk assessment to validate a hypothesis as thoroughly as possible *before* triggering the benchmark, so each spent run is more likely to be conclusive rather than exploratory.
- **Budget for as few as 1 run per hypothesis** when runs are tight. Accept that this gives weaker confidence than the practice-environment guidance above — an intermittent failure that would only show up on a 3rd-6th run (as happened twice this session) may simply not be caught before a real submission. Compensate by being more conservative in the change's *design* (smaller steps, stricter invariant review) rather than relying on repeated runs to catch mistakes after the fact.
- **Consider bundling multiple small, independently-reviewed changes into one benchmark submission** when time/run budget is tight, accepting the tradeoff that a failure is harder to attribute to a specific change — versus the practice-session default of one logical change per verification cycle.
- Track remaining run budget explicitly (if the portal shows a cooldown timer or attempt count) and factor it into whether to attempt a risky change at all versus banking a known-good state.

## Resource Verification

When resource evidence matters for the verdict, use the Resource Monitor Agent skill's exact-window Netdata query pattern, not a post-hoc snapshot — decaying load averages queried a minute after a run ends will overstate current load.

## Output Contract

Score before/after, pass/fail, full error map, regression verdict, and — if the change is being accepted despite ambiguous score movement — the specific evidence (A/B result, resource headroom, or query-level timing) that justifies the accept/reject decision beyond a bare score number.

## ISUCON13 Session-2 Notes (2026-09-24)

- Above ~100k the run-to-run noise is +/-5% (single runs of identical code ranged 150k-170k). Use >= 4 runs per leg and prefer alternating A/B legs over remembered baselines; small (<3%) differences are not attributable.
- Read the bench log (`/tmp/bench.log` on s3, or `result.json` messages) for scenario counts and `DNSAttacker並列数` — the closed-loop bench shifts scenario mix and escalates DNS attack load when parts of the app get faster, which is what explains "obviously cheaper but net slower" outcomes.
- Benchmark noise sources to rule out first: `unattended-upgrade` on either host (ps), analysis jobs (slp/pprof) running during a scored run, and an oversized `mysql-slow.log` (only `deploy_db.sh` truncates it).

## ISUCON13 Session-3 Notes (2026-09-24)

- Always record the bench's scenario counts next to the score (`viewer`, `aggressive-streamer-moderate`, `viewer-spam`, `DNSAttacker並列数`): a change that speeds up search/list routes raises the spam/moderate counts ~2.5x and lowers the score, while changes on the viewer (tip-producing) paths raise `viewer` completions. `/tmp/bench.out` on s4 has them; `scripts/isucon13_bench.sh` prints them.
- At ~240k the run-to-run mode split is ~225k vs ~248k (one or two low-mode runs per six); compare 6-run means and expect ~+-2.5% noise on the mean.
- Do not start a bench while a Profiler/SQL agent is still running `slp`/`pprof` on s4 (the bench host is ~90% busy on its own).
