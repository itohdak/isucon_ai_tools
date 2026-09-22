# Resource Monitor Agent Skill

Report per-host CPU/load/memory/disk during a *specific* benchmark window and give a resource-bound verdict. This role exists to answer one question precisely: is any host CPU-, memory-, disk-, or not resource-bound during a given run — with real numbers, not `NetdataMCP` (that Python tool is broken in this environment; see below).

## Access Pattern That Actually Works

Netdata's parent lives on the bench/pprotein host (`s2`) and receives streamed metrics from every other host. Query it **from inside `s2` over SSH**, hitting `127.0.0.1:19999` — do not try to reach the private IP (`192.168.0.x:19999`) directly from the operator machine, since that subnet is not routable from outside the VPC. (`isucon_ai_tools/isucon_ai_tools/mcp/netdata.py` does exactly that and times out on every call — verified by actually running it. Don't use it; use the pattern below instead.)

```bash
ssh -i <key> ubuntu@<s2-public-ip> "curl -s 'http://127.0.0.1:19999/host/<hostname>/api/v1/data?chart=<chart>&after=<unix>&before=<unix>&format=json&points=10'"
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

Netdata's `apps.plugin` charts weren't configured with process groups in this environment (`apps.*`/`groups.*` charts don't exist per-host here — checked via the charts endpoint). For "which process is actually consuming the CPU," use `pidstat` directly instead:

```bash
ssh -i <key> ubuntu@<host-public-ip> "nohup pidstat -u 1 <seconds> > /tmp/pidstat.log 2>&1 & echo started"
# ... run the benchmark ...
ssh -i <key> ubuntu@<host-public-ip> "pkill pidstat"
scp -i <key> ubuntu@<host-public-ip>:/tmp/pidstat.log <local-path>
```

Then aggregate `%CPU` per `Command` across samples (sum and average) — this is what conclusively identified `mysqld` at ~97.7% avg CPU on the pre-split combined host, and later `mysqld` at ~141-180% on the dedicated DB host.

## Output Contract

Per host: CPU idle avg/min/max, load1 avg/max, memory %, disk util if relevant, and an explicit verdict (CPU-bound / memory-bound / disk-bound / not resource-bound). State the exact time window used.
