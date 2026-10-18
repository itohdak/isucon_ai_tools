# ISUCON14 Practice 2 — Iteration 7: MySQL split to s2

## Agents Used

A dedicated Resource Monitor Agent dispatch was not repeated for this iteration; Codex directly re-queried netdata (same approach as iterations 2-6) to confirm the split threshold was met, consistent with iteration 1's original Resource Monitor Agent finding (mysqld CPU-dominant) still holding true after 6 rounds of SQL-side fixes.

## Hypothesis

Per AGENTS.md's Resource And Split Policy, splitting MySQL to another host is justified once resource evidence shows it's the bottleneck and SQL/app-level fixes have been exhausted. After iterations 1-6 (every missing index, the two N+1 patterns, the `ownerGetChairs` full-scan subquery, and `InterpolateParams`), netdata still showed `s1` CPU-bound (system ~95-99% busy) with `mysqld` (~113% of 2 cores) more than double the app's share (~48%). This meets the evidence threshold; `s2` (idle since environment setup, same `c5.large` instance type/size — not a scale-up) is the designated split target.

## Evidence

- netdata on `s3` (the parent), querying `host/s1` during a live bench run after iteration 6: `app.mysqld_cpu_utilization` peak ~89-113% (user+system) vs. `app.isuride_cpu_utilization` ~48-52%; `system.cpu` busy ~95-99% (near-zero idle).
- This is the same qualitative finding as iteration 1's original Resource Monitor Agent dispatch, now confirmed to persist despite six rounds of query/index optimization — i.e. SQL/app-level fixes are exhausted for this workload shape, satisfying AGENTS.md's "optimize first" precondition before splitting.

## Change

Branch `iter7-db-split`, commits `344f204` + `c013a46`, merged as `1d482e9`.

1. `s2/etc/mysql/mysql.conf.d/mysqld.cnf`: `bind-address`/`mysqlx-bind-address` changed to `0.0.0.0` (the existing security group already permits all traffic within the VPC CIDR `192.168.0.0/24`, so no SG change was needed).
2. `s2/services` = `mysql`; `s1/services` drops `mysql`; `s1/disabled` = `mysql` (stops+disables the now-redundant local mysql on `s1` via `deploy.sh`'s existing per-node override convention).
3. `common/env.sh`: `ISUCON_DB_HOST` -> `192.168.0.12` (s2's private IP).
4. Ran `webapp/sql/0-init.sql` once manually on `s2` (creates the `isuride` DB and the remote-capable `isucon@'%'` user) — a one-time DB-host setup step, not part of the recurring `/api/initialize` flow. No data migration needed: `init.sh` always rebuilds schema+seed data from scratch against `ISUCON_DB_HOST` on every `/api/initialize`.
5. **Gotcha found and fixed during deployment**: `isuride-go.service` and `isuride-payment_mock.service` both had `After=mysql.service` / `Requires=mysql.service` in their unit files. Systemd's `Requires=` starts the required unit whenever the dependent unit starts, *regardless of the required unit's enabled/disabled state* — so `deploy.sh`'s `disable --now mysql` on `s1` was silently undone by the very next step (`systemctl restart isuride-go.service`), which auto-started the disabled local mysql right back up. Removed both lines from both unit files since the app and payment mock no longer depend on a local DB.

## Verification

- `s1 -> s2:3306` connectivity confirmed with a plain `mysql -h 192.168.0.12 -uisucon -pisucon -e 'SELECT 1'` before deploying the app change.
- After the systemd-unit fix: `systemctl is-active mysql` on `s1` -> `inactive` (stayed down through a full `isuride-go` restart).
- `POST /api/initialize` -> `200` (schema/seed data created fresh on `s2`).
- 3 benchmark runs (logs truncated on both `s1` and `s2` between each): 7517 (`CODE=26 x1`), 7338 (no errors), 7239 (`CODE=26 x2`) — all `pass=true`. The `CODE=26` warnings are the same pre-existing, unrelated `ownerGetChairs` lag warning seen intermittently since the baseline.

## Benchmark Result

Mean **~7365** across 3 runs — roughly double iteration 6's mean (~3777), and by far the largest and most consistent single-iteration gain in this project so far (narrow spread: 7239-7517 vs. earlier iterations' wider bands).

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `c013a46` (merged as `1d482e9`).

## Commit

`344f204` + `c013a46` on branch `iter7-db-split`, merged to `main` as `1d482e9`.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/7 (merged, branch deleted).

## Next Candidate

Re-run the Resource Monitor check on both `s1` and `s2` now that the split is live, to see which host is the new bottleneck (app CPU on `s1`? mysqld CPU on `s2` now running alone on its own 2 cores?) and whether `s3`'s otherwise-idle capacity (bench+pprotein only, bench host is mostly idle except during the ~90s load phase) suggests any further rebalancing. `config/isucon14_2.yaml` and `AGENTS.md`'s environment notes should be updated to reflect the new topology.
