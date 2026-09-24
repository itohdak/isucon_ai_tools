# ISUCON12 qualify — iterations 1-4 (first improvement session, 2026-09-24)

App repo: `git@github.com:itohdak/isucon12_qualify_practice_2.git`. Bench: `./bench` on s3 against s1 (single serving host), 60 s load. Scores are single runs unless noted (contest-style scarcity of runs is not an issue on this practice env, but each cycle here was one deploy + one bench + alp/slp/pprof/netdata evidence).

Sub-agents were not used because: the harness for this session says to work inline unless the user asks for sub-agents; Profiler / Resource Monitor / SQL / App-Understanding analysis was done directly (alp + slp via `scripts/analyze.sh`, pprotein pprof via `scripts/pprof_top.sh`, netdata via `scripts/resources.sh`, code reading of the 1.6k-line reference app and the bench source).

## Baseline

| State | Score |
| --- | --- |
| Pristine reference app (docker, no logs) | 2586 (pass) |
| Native binary, nginx LTSV + MySQL slow log (`long_query_time=0`) + pprotein on (commit 249cb15) | 1834 (pass) |

Evidence at baseline: alp — ranking avg 2.47 s, player detail 1.74 s, score POST 3.4 s, admin billing 17.9 s; slp — `visit_history GROUP BY` 136 s and `REPLACE INTO id_generator` (7018 calls) 123 s; pprof — only 21% CPU busy, 80% of samples inside SQLite (`sqlite3_step`) i.e. waiting/full scans, not CPU-bound.

## Iteration 1 — indexes (commit 79c5743): score 2593 (flat)

Hypothesis: `player_score` has no index (SQLite full scans, 1.67M rows in tenant 1) and MySQL `visit_history` (2.9M rows) has no index on competition_id. Change: SQLite indexes `(tenant_id, competition_id, row_num)` and `(tenant_id, competition_id, player_id, row_num)` (pre-built into `initial_data_idx` so `/initialize` only copies files), `visit_history` collapsed to one row per `(tenant_id, competition_id, player_id)` with the first-visit time (billing only ever uses `MIN(created_at)`), written with `INSERT ... ON DUPLICATE KEY`. Result: score unchanged. Evidence in alp showed why: the latency was not the scans but `flock` — the score upload held the per-tenant lock while doing one `REPLACE INTO id_generator` and one autocommit INSERT (fsync) per row, and every ranking/player read on that tenant queued behind it. Also, `unattended-upgrade`/`apt-check` was still burning ~50% of s1 (found in iteration 2; see below).

## Iteration 2 — score upload path (git log "Cycle 2: score upload path"): 2593 -> 9811, then 15595 after apt was stopped

Change: `dispenseID` takes 1000-id blocks from `id_generator` (`UPDATE ... LAST_INSERT_ID(id+1000)`) and hands them out in-process (reboot-safe, DB counter stays authoritative, reset on `/initialize`); score upload reads all player ids once, then `DELETE` + 500-row multi-row `INSERT`s in one immediate transaction; `flock` removed (WAL snapshot reads + transaction atomicity replace it); tenant SQLite handles cached per tenant (`_journal_mode=WAL&_busy_timeout&_synchronous=NORMAL&_txlock=immediate`) and closed before `/initialize` swaps the files. Result 9811 (pass, 0 errors). Then netdata showed 24% `nice` CPU on s1: **`unattended-upgrade`/`apt-check` on a freshly created instance** — stopped/disabled on all 3 hosts (also added to the ansible `general` role), same code re-benched: **15595** (one 30 s admin-billing timeout error, -1%).

## Iteration 3 — billing memoization: 15595 -> 21723

Billing is only non-zero for finished competitions (`if comp.FinishedAt.Valid`), and after finish score uploads are rejected and later visits are ignored, so a finished competition's report is immutable. Unfinished competitions now return zeros without any query; finished ones are cached (only once `now > finished_at+1 s`, to avoid a same-second visit race) until the next `/initialize`. admin billing avg 17.9 s -> 0.29 s. Result 21723 (pass, 0 errors).

## Iteration 4 — read path + nginx: 21723 -> 43024

pprof after iteration 3: 71% of CPU in `competitionRankingHandler`, mostly `retrievePlayer` per ranking row (N+1). Change: ranking computed with one query (`GROUP BY player_id` on the covering index joined back to `player_score` and `player`) and cached per (tenant, competition) with a generation counter that is bumped when a score upload commits; player page scores in one JOIN; in-process caches for the parsed JWT key and verified tokens (expiry re-checked), tenant-by-name, player, competition (invalidated on disqualify/finish); `visit_history` written only for the first visit of a (tenant, competition, player) per `/initialize`. The first run at this point failed: nginx `768 worker_connections are not enough` (the app had become fast enough to expose it) -> `worker_connections 16384`, `worker_rlimit_nofile 65536`, upstream keepalive to the app, TLS session cache. The next run failed on the bench client (`too many open files`, s3's ulimit 1024) -> `ulimit -n 65536` in `scripts/bench.sh` and port-range/`tcp_tw_reuse` sysctl on s3 (bench harness only). Result **43024** (pass, 0 errors).

## Reusable lessons

- A cheap SQL index did nothing while a lock convoy (`flock` held across per-row round trips) dominated — alp per-route averages + a look at the *write* handler's loop found it, pprof did not (idle waiting is not CPU).
- Freshly created instances run `unattended-upgrade`/`apt-check` for a long time; check `ps` / netdata `nice` CPU before trusting any score (this is in AGENTS.md for ISUCON13 too).
- Making the app faster moves the bottleneck to the front door: watch nginx `error.log` (`worker_connections`) and the bench client's own fd/port limits.
- `deploy.sh` must create log files owned by the daemon before truncating them; a root-owned `mysql-slow.log` silently turns `slow_query_log` OFF.
