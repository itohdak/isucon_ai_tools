# Resource Monitor Agent Skill

Report per-host CPU/load/memory/disk during a *specific* benchmark window and give a resource-bound verdict. This role exists to answer one question precisely: is any host CPU-, memory-, disk-, or not resource-bound during a given run — with real numbers, not `NetdataMCP` (that Python tool is broken in this environment; see below).

## Access Pattern That Actually Works

Netdata's parent lives on the bench/pprotein host (`s3`) and receives streamed metrics from every other host. Query it **from inside `s3` over SSH**, hitting `127.0.0.1:19999` — do not try to reach the private IP (`192.168.0.x:19999`) directly from the operator machine, since that subnet is not routable from outside the VPC. (`isucon_ai_tools/isucon_ai_tools/mcp/netdata.py` does exactly that and times out on every call — verified by actually running it. Don't use it; use the pattern below instead.)

```bash
ssh -i <key> ubuntu@<s3-public-ip> "curl -s 'http://127.0.0.1:19999/host/<hostname>/api/v1/data?chart=<chart>&after=<unix>&before=<unix>&format=json&points=10'"
```

- `<hostname>` is the short name (`s1`, `s2`, `s3`, ...) — confirm which hosts are actually mirrored with `curl http://127.0.0.1:19999/api/v1/info` (look at `mirrored_hosts`). A host that isn't listed has no Netdata data at all — check whether it's even in the ansible inventory and whether the `general` role has been run against it (see `docs/isucon-startup-checklist.md` and the DB-split history in `MILESTONES.md` for the `[db]` group precedent).
- Discover real chart names per host with `curl http://127.0.0.1:19999/host/<hostname>/api/v1/charts` rather than assuming — they can differ (e.g. `disk_util.nvme0n1`, device-name-dependent).
- Common charts: `system.cpu` (fields: user/system/iowait/softirq/...; idle = 100 minus the sum of the others), `system.load` (load1/load5/load15), `system.ram`, `disk_util.<device>`.

## Timing Gotcha: Decaying Averages

`load1`/`load5` are **decaying exponential averages**, not instantaneous snapshots. If you query "now" shortly after a benchmark run ends, you will see a misleadingly high load average that is just decaying residue from the run, not current steady state — this produced a false alarm mid-session (apparent load1 of 40+ that turned out to be normal decay, confirmed wrong via `vmstat 1` showing real-time 98%+ idle at the same moment).

**Always query the exact benchmark start/end unix timestamps** (pad ±10-15s), not an arbitrary "last N seconds from whenever you happen to run the query":

```bash
date -u +"%Y-%m-%dT%H:%M:%S start"   # capture before running the bench
# ... run the benchmark ...
date -u +"%Y-%m-%dT%H:%M:%S end"     # capture after
START=$(date -u -d "<start>" +%s); END=$(date -u -d "<end>" +%s)
```

For a true "is it saturated right now" spot-check instead of a historical window, SSH in and run `vmstat 1 5` or `mpstat -P ALL 1 3` directly — real-time sampling, no decay ambiguity.

## Per-Process Breakdown

**Update (2026-09-23): per-process CPU is now available directly in netdata**, superseding the `pidstat` workaround below for the processes it covers. The earlier claim that `apps.*` charts "don't exist per-host here" was wrong for what it actually meant: `apps.plugin` was running all along (322 `app.*` charts existed on `s1`), but `isuride` and `payment_mock` didn't match any pattern in netdata's stock `apps_groups.conf`, so they were silently lumped into a generic `other` group alongside everything else unclassified — indistinguishable from each other or from unrelated system noise.

Custom group entries (`isuride`, `isuride-payment_mock`, `nginx`) were added on webapp-group hosts (`s1` as of the current role mapping) via `isucon_ansible`'s `general` role, concatenated ahead of a fresh copy of netdata's stock `apps_groups.conf` (that file, if present under `/etc/netdata/`, fully *replaces* the stock one rather than merging with it — there's no include mechanism, which is why an early attempt at this that just wrote a 3-line file wiped out ~20 useful stock groups like `auth`/`cron`/`sql` until fixed to concatenate instead of replace).

- Chart family: `app.<group>_cpu_utilization` (also `_mem_usage`, `_disk_physical_io`, `_threads`, etc.) for groups `isuride`, `isuride-payment_mock`, `nginx`, plus the ~20 stock groups (`sql` covers `mysqld*` — this is what made `app.mysqld_cpu_utilization` appear automatically on the db host without any custom config).
- Query the same way as any other chart: `curl 'http://127.0.0.1:19999/host/<hostname>/api/v1/data?chart=app.isuride_cpu_utilization&after=<unix>&before=<unix>&points=10'` (`user`+`system` fields, in %; sum them for total CPU%).
- **Known gap**: `isuride-matcher.service`'s shell loop (`sh -c "while true; do curl ...; sleep ...; done"`) is not usefully groupable this way — its actual cost is in the very short-lived `curl` child processes it spawns every tick, which apps.plugin's periodic sampling is unlikely to attribute reliably. Use `pidstat` (below) if the matcher loop's own overhead specifically needs measuring.
- Re-running `ansible-playbook playbooks/deploy_general.yaml --limit <webapp-host>` after any environment recreation reproduces this (verified idempotent). Only applies to whichever host(s) are currently in the `webapp` inventory group — re-run against a new host if roles are swapped again.

For anything not covered by a netdata process group (the matcher loop above, or any other short-lived/unclassified process), fall back to `pidstat` directly:

```bash
ssh -i <key> ubuntu@<host-public-ip> "nohup pidstat -u 1 <seconds> > /tmp/pidstat.log 2>&1 & echo started"
# ... run the benchmark ...
ssh -i <key> ubuntu@<host-public-ip> "pkill pidstat"
scp -i <key> ubuntu@<host-public-ip>:/tmp/pidstat.log <local-path>
```

Then aggregate `%CPU` per `Command` across samples (sum and average) — this is what conclusively identified `mysqld` at ~97.7% avg CPU on the pre-split combined host, and later `mysqld` at ~141-180% on the dedicated DB host.

## MySQL-Level Metrics (db host only, since 2026-09-23)

The `db`-group host (`s2` as of the current role mapping) runs netdata installed via the **official kickstart installer**, not the Ubuntu apt package — the apt package (`netdata-core`/`-plugins-bash`/`-plugins-python`) has no `go.d.plugin` at all, so it cannot collect MySQL metrics; only OS-level metrics were visible before this. This matters because a real regression was once invisible until an ad-hoc SSH `SHOW STATUS` check found it (`Max_used_connections` had hit MySQL's stock `max_connections=151` ceiling, causing a failed benchmark run) — with this collector, the same signal is now visible as a live/historical chart instead of needing a reactive one-off check.

- Chart family: `mysql_local.*` (43 charts as of setup), e.g. `mysql_local.connections`, `mysql_local.connections_active`, `mysql_local.innodb_buffer_pool_bytes`, `mysql_local.innodb_io`, `mysql_local.innodb_cur_row_lock`, `mysql_local.handlers`, `mysql_local.net`. List them all with the same `.../api/v1/charts` pattern above, filtering for names starting with `mysql`.
- Query the same way as any other chart, through the `s3` parent: `curl 'http://127.0.0.1:19999/host/s2/api/v1/data?chart=mysql_local.connections&after=<unix>&before=<unix>&points=10'`.
- Collector config: `/etc/netdata/go.d/mysql.conf` on the db host, connecting as a minimal-privilege `netdata`@`localhost` user (`PROCESS, REPLICATION CLIENT` only, no password, unix socket at `/var/run/mysqld/mysqld.sock`). Managed by `isucon_ansible`'s `general` role (`roles/general/tasks/main.yaml`), which installs netdata differently for `db`-group hosts specifically — re-running `ansible-playbook playbooks/deploy_general.yaml --limit <db-host>` after any environment recreation reproduces this (verified idempotent).
- **This only applies to whichever host is currently in the `db` inventory group.** If DB moves hosts again (per this project's history of role swaps), re-run the `general` role against the new db host to get the same collector there; the old db host keeps whatever install it had unless the role is re-run there too.
- **Update (2026-09-23, later same day)**: `webapp`-group hosts (`s1`) were also switched to the kickstart install, so `s1`/`s2` — the two load-targeted hosts — now use the same netdata version/install method by design (deliberate symmetry, not scope creep: kept `s1` and `s2` consistent with each other since they're the pair that matters for tuning). `s1`'s per-process `app.*` groups (see below) benefit from the same, newer, more granular stock `apps_groups.conf` this brought. Only `pprotein`-group hosts (`s3`) remain on the plain apt package.

## Output Contract

Per host: CPU idle avg/min/max, load1 avg/max, memory %, disk util if relevant, and an explicit verdict (CPU-bound / memory-bound / disk-bound / not resource-bound). State the exact time window used.
