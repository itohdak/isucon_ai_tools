# Resource And Instance Split Policy

Use this policy before splitting ISUCON roles across servers.

## Rule

Do not split `web`, `app`, and `db` just because multiple instances are available.

Split instances only when benchmark-time resource evidence shows that a resource is the bottleneck and the split directly relieves that bottleneck.

## Required Evidence During Bench

Collect these while the benchmark is running:

- CPU: per-host CPU usage, idle, iowait, steal, load average, run queue.
- Process CPU: app, MySQL, nginx, benchmark, pprotein.
- Memory: free memory, swap, major pressure.
- Disk IO: iowait, read/write throughput, queue pressure when available.
- Network: app-to-db traffic if DB is remote or being considered for remote placement.
- Application evidence: pprotein/alp route totals, slp slow query totals, pprof CPU profile.

Use Netdata when installed. Otherwise collect lightweight samples with:

```bash
vmstat 1
pidstat -durh 1
mpstat -P ALL 1
iostat -xz 1
ss -tanp
```

## Split Decision

Consider splitting DB from app only when at least one of these is true during a valid benchmark:

- App CPU is saturated while MySQL has headroom and app code is CPU-bound.
- MySQL CPU is saturated and route/slowlog evidence shows DB time dominates.
- Disk IO or iowait on the DB path is high and MySQL writes/reads dominate.
- Memory pressure or swapping is visible on the combined host.
- App and DB both compete for CPU enough that separating them should increase throughput.

Do not split when:

- CPU idle remains high during bench.
- slowlog/httplog shows query or endpoint inefficiency without resource saturation.
- pprof shows app hot paths that can be optimized in-process.
- The added network hop is likely to cost more than the resource relief.

## If DB Is Split

Follow the MySQL split checklist in `docs/mysql-operations-tips.md`.

After splitting, benchmark immediately and compare:

- pass/fail and error categories
- score delta
- route total time
- SQL total time
- CPU/iowait before and after
- network-related latency

Rollback the split if it does not improve a valid benchmark or if it introduces instability.

## Executed: 2026-09-23 DB Split To `s3`

This split was actually carried out. Evidence and full details are in `reports/iterations/iteration-20260923-000218.md`; summary:

- `pidstat` isolated `mysqld` at ~97.7% CPU avg on `s1` (vs ~43% for the app) before splitting — a clean match for the "MySQL CPU is saturated" criterion above.
- Only 2 of 3 EC2 instances were provisioned for this practice environment; the 3rd was added via a CloudFormation stack update (the template already had a commented-out `Instance3`/`InstanceIP3`), not a bare `aws ec2 run-instances` call, after explicit human approval of both the general approach and the specific change-set.
- Post-split, `s1` had CPU headroom again and typical scores rose, but a previously-unseen intermittent `CODE=32` (matching latency) failure appeared — a reminder that relieving one resource bottleneck can expose a different one (here, the matcher's fixed polling cadence) rather than guaranteeing an unconditionally better result. Treat "the split worked" and "the system is now fully stable" as separate questions.
