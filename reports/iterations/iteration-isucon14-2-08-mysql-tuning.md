# ISUCON14 Practice 2 — Iteration 8: MySQL server tuning on s2

## Agents Used

Sub-agents were not used because: this iteration's evidence came from a direct `SHOW VARIABLES` check (not a fresh profiling pass), and a second resource incident on `s2` (see below) made further heavy log-analysis commands too risky to delegate blindly without extra caution — Codex handled this directly, one command at a time.

## Hypothesis

After iteration 7's split, `mysqld` alone saturates both of `s2`'s cores (~175% of 200%) while `s1` runs with substantial idle headroom (~50%). With indexes/N+1/round-trips already addressed, the remaining lever is MySQL server configuration: `s2` is a single-purpose, dedicated DB host with no replication or crash-recovery requirement in this practice setup, making the standard durability-for-throughput trade applicable.

## Evidence

- `SHOW VARIABLES` on `s2`: `innodb_buffer_pool_size=134217728` (128M, the Debian package default — tiny relative to `s2`'s 3.7G RAM, which now runs nothing but mysqld), `innodb_flush_log_at_trx_commit=1`, `sync_binlog=1`, `log_bin=ON` (MySQL 8.0 enables binary logging by default even with no explicit config), `innodb_flush_method=fsync`.
- **Incident**: attempting to profile `s2`'s slow log with `slp` (even on a size-capped 29MB sample, after the first attempt on the full 146MB log also hung) caused `s2` to become fully unresponsive a second and third time, needing two more manual AWS-console reboots (same irreversible-without-console-access situation as `s1`'s earlier incidents — the operator IAM user still cannot reboot or inspect console output). This strongly suggests `slp`/`alp` log analysis should be avoided entirely on these 2 vCPU hosts while mysqld is already near its CPU ceiling; this iteration's change was based on `SHOW VARIABLES` and code/config reading only, not a fresh slow-log breakdown.

## Change

Branch `iter8-mysql-tuning`, commit `565c248`. Added to `s2/etc/mysql/mysql.conf.d/mysqld.cnf`:
- `innodb_buffer_pool_size = 2G`
- `innodb_flush_log_at_trx_commit = 2`
- `innodb_flush_method = O_DIRECT`
- `skip-log-bin`

No application code changed.

## Verification

- `SHOW VARIABLES` after deploy confirmed `innodb_buffer_pool_size=2147483648` and `log_bin=OFF`.
- `POST /api/initialize` -> `200`.
- 3 benchmark runs (logs truncated between each, on both `s1` and `s2`): 7552, 7023 (`CODE=26 x1`, pre-existing unrelated warning), 7929 — all `pass=true`.

## Benchmark Result

Mean **~7501** across 3 runs, a modest further improvement over iteration 7's mean (~7365). Smaller gain than iteration 7's split (expected — this is config tuning on top of an already-relieved bottleneck, not a structural fix), but consistently positive across all 3 runs with no regression.

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `565c248`.

## Commit

`565c248` on branch `iter8-mysql-tuning`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/8 (merged, branch deleted).

## Next Candidate

Given the repeated `slp`/`alp` hang incidents on these 2 vCPU hosts (now 4 total across the session: `s1` twice in iterations 1-2, `s2` twice in this iteration), future iterations should avoid full-log analysis tools entirely on this environment and rely on `SHOW VARIABLES`/`EXPLAIN`/code reading plus short, targeted `SHOW PROCESSLIST` or `SHOW ENGINE INNODB STATUS` snapshots instead. `internalGetMatching`'s `ORDER BY RAND()` chair-selection query (fixed-cadence poller, every 0.5s regardless of load) is a candidate but touches matching-selection behavior, which AGENTS.md flags as an ask-first item — do not change the selection semantics without explicit human approval, even if only optimizing its query shape.
