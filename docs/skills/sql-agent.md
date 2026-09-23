# SQL Agent Skill

Analyze query plans and access patterns; suggest low-risk database-side improvements. Do not modify the live database or write code — report findings for Codex/the human to act on.

## Where MySQL Actually Lives

MySQL runs on the dedicated DB host **`s2`**, not the app host `s1` — it was split out after resource evidence showed the combined host was CPU-bound. (`isucon_ai_tools/isucon_ai_tools/mcp/mysql.py` still hardcodes SSH to `hosts.app`, i.e. `s1` — that tool is stale post-split and will silently read `s1`'s now-unused local slow log instead of erroring. Don't use it; connect to `s2` directly.)

```bash
ssh -i <key> ubuntu@<s2-public-ip> "sudo mysql isuride -e '...'"
```

Slow query log: `/var/log/mysql/mysql-slow.log` on `s2`, `long_query_time=0.0` (logs every query). `slp` is installed on `s2` directly (deployed via the `pprotein` ansible role's `--limit s2` run, alongside `pprotein-agent` so pprotein itself can also collect it).

## Required Methodology: Produce The Full Ranking, Not A Narrative Summary

A prior run of this skill reported a narrative "top findings" list that quietly mixed a true `Sum(Query_time)` ranking with an unstated "also flag anything with a scary max latency" heuristic, applied inconsistently — it under-ranked its own 3rd finding (actually 9th by summed time) and missed a query that would have qualified under its own stated heuristic. Avoid repeating this:

1. Get the complete ranked table first, and include it (or its top 10-15 rows) verbatim in your report:
   ```bash
   slp my --file /var/log/mysql/mysql-slow.log --sort sum-query-time --reverse --limit 5000
   ```
   (Use a large `--limit` — the default errors with "Too many Queries" once distinct shapes exceed it. For a huge log file, `sudo tail -c <bytes> /var/log/mysql/mysql-slow.log > /tmp/recent.log` first to bound the input.)
2. If you want to flag something outside that top-10-15 for a *different* reason (e.g. unusually high per-call/max latency, or a known correctness-risk area), say so **explicitly and separately** — don't blend it into the same list without distinction.
3. For each candidate from either list, run `EXPLAIN` (and `EXPLAIN ANALYZE` if it returns quickly) with representative parameter values against the live `s2` database to check index usage (`ref`/`range`/`const` vs `ALL`), rows examined, `Using filesort`/`Using temporary`.

## Attribution Via SQL Comments

Hot-path queries are annotated with `/* api:<handler> */` or `/* api:<handler> fn:<helper> */` comments (added deliberately for this reason). `slp`'s normalized output strips comments, so to attribute a normalized query shape back to its handler, `grep -B2 '<distinctive fragment>' /var/log/mysql/mysql-slow.log` against the raw file instead.

## Schema Change Gotcha: New Columns Must Go Through `init.sh`, Not `1-schema.sql`

`webapp/sql/3-initial-data.sql.gz` uses **positional** `INSERT INTO <table> VALUES (...)` statements tied to the original column count and order. If you add a new column directly to `1-schema.sql`'s `CREATE TABLE`, the seed-data load (which runs *after* the schema in `init.sh`, *before* any `ALTER TABLE`) will fail with "Column count doesn't match value count." This actually happened this session when adding `chairs.latest_latitude`/`latest_longitude`.

The correct pattern (already used for `chairs.total_distance`): add the new column via `ALTER TABLE` inside the inline SQL block at the **end** of `webapp/sql/init.sh`, *after* the `3-initial-data.sql.gz` load, and backfill it there if historical data supports it (e.g. from `chair_locations` history) in the same `UPDATE`. Never add a new column straight to a `CREATE TABLE` in `1-schema.sql` without checking whether `3-initial-data.sql.gz` has a positional `INSERT` for that table.

## ISUCON13 (ISUPipe) Environment Note: `slow_query_log` Overhead Is Real On This Host

On the ISUCON13 practice environment (`s1` = app+DB combined, only 2 vCPUs, confirmed CPU-saturated during benchmark runs), leaving `slow_query_log=1`/`long_query_time=0` enabled during a **scored** benchmark run cost ~20-25% of the score in an isolated A/B test (8707 vs 10676-11356 on an otherwise-identical config) — logging every single query has a real CPU/IO cost on a constrained host, not just a disk-space cost. Also beware: `common/etc/mysql/mysql.conf.d/mysqld.cnf` is git-tracked and gets copied over the live config (then `mysqld` is restarted) on every `deploy.sh` run — a live-only `SET GLOBAL`/`sed` fix to enable slow-query logging will silently revert on the next deploy unless the tracked file itself is also updated.

Protocol: only enable slow-query logging transiently, immediately before a dedicated analysis-only benchmark run (`SET GLOBAL slow_query_log = 1; SET GLOBAL long_query_time = 0;` — this is a live, non-persistent change and is fine to leave un-committed), collect the log, then disable it again (`SET GLOBAL slow_query_log = 0;`) before the next benchmark run whose score is meant to count. Do not persist `slow_query_log=1` in the tracked `mysqld.cnf` for this project.

## ISUCON13 (ISUPipe) Environment Note: Don't "Fix" PowerDNS Speed Without Re-Checking The Benchmark's Adaptive Load

Adding a missing index to PowerDNS's own `isudns.records` table (`name`/`type` — a full-table-scan on every DNS lookup) was tested and produced a clear, reproducible **regression** (avg ~8700-10200 vs ~11000-12200 without it), traced via the benchmark's own `result.json` fields: with the index applied, `DNSAttacker並列数` (an internal adaptive DNS-attack concurrency counter) rose from 2 to 3 and successful DNS resolutions roughly tripled — the benchmark appears to escalate adversarial DNS load once it observes the DNS server coping well, and that extra load competes for the same CPU-constrained host's cycles as the app/mysqld, hurting the app traffic that actually drives score more than the DNS fix itself helps. Don't re-attempt this without first checking whether `DNSAttacker並列数` is bounded/capped in a way that would prevent this escalation.

## Do Not Suggest

- Re-adding an in-process (Go-side) cache for auth/lookup data — tried twice this session (access-token cache, and separately a `FOR SHARE` lock removal that turned out to cost, not save, performance under A/B testing) and rejected both times. If you think an app-level cache would help, flag it as a hypothesis for Codex to A/B test carefully, not a confident recommendation.
- Increasing `innodb_buffer_pool_size` as a priority fix unless you've checked the actual working-set size and buffer-pool hit ratio (`SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool%'`) — this dataset is small enough (~15-20MB) that the default 128MB pool already has a >99.999% hit ratio in practice; it wasn't the bottleneck.
