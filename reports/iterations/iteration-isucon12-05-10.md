# ISUCON12 qualify — iterations 5-10 (2026-09-24)

Continuation of `iteration-isucon12-01-04.md`. Sub-agents were not used (same reason and same caveat as in that file: the four analysis roles were done inline; the user asked afterwards why).

Bench caveat that applies to every number below: the bench host is a 2-vCPU instance and it, not the servers, becomes the ceiling from iteration 6 on (gross ~234-240k). Runs sometimes lose 1-33% to client-side `dial tcp ...: i/o timeout` errors that fire at the end of the load window; the server side shows no 5xx. Judge by gross score, error class, and server CPU, and repeat runs.

## Iteration 5 — player scores query plan: ~43k -> ~161k

pprotein pprof (with the first *complete* profile of the fast app): `playerHandler` = 83% of app CPU. `EXPLAIN QUERY PLAN` showed the JOIN written in iteration 4 was driven from `player_score` via `(tenant_id=?)` — a scan of the tenant's 1.67M rows (0.2 s on tenant 1) instead of a per-competition index seek. `CROSS JOIN` forces competition-first order: 3 ms. Also `e.Debug=false` (JSON was being pretty-printed) and echo's per-request JSON access logger removed (it fed journald at ~4% CPU; nginx already logs). Result 161368 (pass, 0 errors); repeat 158270. Also fixed a `database is locked` 500 on admin billing: new tenant DBs were created by the `sqlite3` CLI in rollback-journal mode and the app's first connections raced to switch to WAL while billing listed the half-created tenant. Now the tenant row and its DB file are created inside one MySQL transaction, the DB is created in-process directly in WAL mode.

## Iteration 6 — role split: s2 = nginx + MySQL, s1 = app: ~160k -> ~217k

Resource Monitor evidence (vmstat 5 s / `top` during the 60 s load): s1 `us 70 sy 27 id 0-2`, run queue 3-10, `isuports` 110% + nginx 60% + mysqld 13% of 200%; s2 96% idle. Executed under the standing authorization (same instance types; no scale-up): s2 runs nginx (upstream `192.168.0.11:3000`) and MySQL (`bind-address 0.0.0.0`, the AMI's `isucon@'%'` user), s1 runs only the app with `ISUCON_DB_HOST=192.168.0.12`; `deploy.sh` grew per-host `services` and `disabled` lists (so a reboot does not bring nginx/MySQL back on s1 or the docker app on s2) and builds the Go binary only where `isuports` runs. Result 216958 (pass) / 204309 with 4 client dial timeouts. pprotein targets now: pprof s1, httplog + slowlog s2.

## Bench host becomes the limit — s4 added (c5.large)

After the split s1/s2 still had 25-45% idle but the bench host (s3, 2 vCPU) was at user 83% + sys 5% + softirq 5%, and `dial ... i/o timeout` errors appeared. Per the user ("a 4th instance if needed", later "c5.xlarge is fine") a 4th instance was added with a CloudFormation change set (only `QualifyInstance4` + `QualifyInstanceIP4` were Adds; template `isucon_cf_provisioning/isucon12_qualify/cf-template-isucon12-qualify-4host.yaml`): s4 = bench + pprotein + netdata parent; s3 is now a spare, symmetric competition server (git checkout, Go, netdata child, pprotein-agent) currently unused. **Resizing s4 to c5.xlarge failed**: the stack's IAM user (`isucon_user`) lacks `ec2:StopInstances`, CloudFormation rolled back and the rollback itself failed (`UPDATE_ROLLBACK_FAILED`), and `cloudformation:ContinueUpdateRollback` is also denied. No workaround was attempted. All 4 instances are unchanged and healthy (s4 still c5.large). The stack cannot be updated until someone with more permission runs `aws cloudformation continue-update-rollback --stack-name isucon12-qualify --resources-to-skip QualifyInstance4` (the instance itself was never touched), after which the resize can be retried from the console (stop, change type, start) and the template updated to match.

## Iteration 7 — MySQL commit path + buffered nginx log: 233844 (0 errors)

s2 showed 18-22% iowait with nginx workers in D state (per-request access-log writes + per-commit fsync). MySQL: `innodb_flush_log_at_trx_commit=2`, `O_DIRECT`, 1 GB pool, `disable_log_bin`, `performance_schema=OFF`; nginx `access_log ... buffer=256k flush=1s` (the log is still always produced). iowait gone. 233844 (pass), repeat 220404 with 7 client dial timeouts (gross 236993).

## Iteration 8 — per-player scores cache: 240259 (0 errors)

`playerHandler` was still 40% of app CPU. The scores list is cached per (tenant, player) with a per-tenant generation bumped on score upload (generation read before the query, so an upload during a compute leaves the entry invalid). App CPU 140% -> 121% at the same throughput. 240259 / 230315 (4 dial timeouts, gross 239911).

## Iteration 9 — ranking response body cache + GOGC=400: 240397 / 239127 (0 errors both)

The ranking handler builds the JSON once per (tenant, competition, rank_after, finished) and serves the bytes while the competition's ranking generation is unchanged. `GOGC=400` on the app (RSS ~780 MB of 3.6 GB). App CPU ~116%.

## Iteration 10 — reboot verification (no code change)

Both s1 and s2 rebooted. Everything came back unaided: s1 `isuports` (nginx/mysql stay disabled), s2 `nginx` + `mysql` (`isuports` stays disabled), `slow_query_log` ON, 177 tenants and `tenant_db` files intact. First bench right after the reboot (no redeploy): **237856, pass, 0 errors** — 99% of the pre-reboot ~240k, well above the contest's "reproduced score must exceed 85%" rule. A second run immediately after had 17 client-side dial timeouts at the end of the window (gross 213751).

## Reusable lessons

- Read the plan before believing an index exists: a semantically correct JOIN still chose a tenant-wide scan (`EXPLAIN QUERY PLAN`, then `CROSS JOIN` to pin the outer loop).
- Sample per-process CPU *during the 60 s load window* (`top -b -d 15 -n 2`, second iteration) — netdata averages over the window included the 20 s prepare phase and hid a fully saturated host.
- When the bench host saturates, scores plateau and errors appear that are not the server's fault; check the bench host's CPU before tuning the server further.
- Splitting off nginx (TLS) and MySQL from the app host was worth ~+35% at the time and needed only config: per-host `services`/`disabled` lists keep reboots honest.
- `pprotein` collects a 90 s pprof from `/initialize`; starting the next run before it finishes makes the next collect fail ("cpu profiling already in use") — `run_cycle.sh` now waits for `Status: pending` to clear.
- The CloudFormation IAM user cannot stop instances; an in-place instance-type change there ends in `UPDATE_ROLLBACK_FAILED`. Create the bench host at the intended size instead.
