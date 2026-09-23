# Profiler Agent Skill

Rank API and SQL bottlenecks by total latency, using real artifacts and real commands. Do not propose code changes — that is the next step in the loop, not this one.

## Where The Evidence Lives

- pprotein artifacts (httplog, slowlog, pprof) land on the bench/pprotein host (`s3`) under `/home/isucon/data/`, named `<id>-httplog.log` / `<id>-slowlog.log` / `<id>-pprof.pb.gz`. List them sorted by time to find the artifact matching the run you care about:
  ```bash
  ssh -i <key> ubuntu@<s3-public-ip> "ls -la --time-style=full-iso /home/isucon/data/*.log | sort -k6,7 | tail -10"
  ```
- `alp` and `slp` binaries are pre-installed on `s3` (and on any host the `pprotein` ansible role has been run against, including the DB host once it has pprotein-agent — see the SQL Agent skill).
- If pprotein collection looks stale (artifact size much smaller than expected, or timestamps don't match a recent run), check that `pprotein-agent` is actually deployed and serving `/debug/log/{httplog,slowlog}` on **every** host that owns a log pprotein is supposed to collect — see "Known Environment Facts" below. A stale collector silently serves an old file instead of erroring, so a suspiciously-small artifact is the only symptom.

## Commands

Route totals from an httplog:

```bash
alp ltsv --file <httplog> --sort sum --reverse --limit 5000 -m '<pattern1>,<pattern2>,...'
```

- Pass all match patterns as **one** `-m` flag with comma-separated regexes, not repeated `-m` flags.
- Use a generously large `--limit` — both `alp` and `slp` error with "Too many URI's/Queries (N or less)" instead of truncating when distinct entries exceed the default limit.
- Route patterns for this app are in `config/isucon14.yaml`'s `api_aggregation.matching_groups`.

SQL totals from a slowlog:

```bash
slp my --file <slowlog> --sort sum-query-time --reverse --limit 5000
```

- The subcommand is `slp my`, not `slp query`.
- If you need to attribute a query to a specific handler/function, grep the *raw* slowlog for `/* api:... */` / `/* fn:... */` comments — `slp`'s normalized output strips SQL comments, so comment-based attribution must be done separately with `grep -B2 '<normalized-fragment>'` against the raw file.

## Known Environment Facts (keep current)

- App host: `s1`. Bench/pprotein host: `s3`. DB host: `s2` (split from `s1`; see the SQL Agent skill for why).
- MySQL's slow log lives on **`s2`**, not `s1`, since the DB split. `pprotein-agent` must be running on `s2` (not just `s1`/`s3`) for pprotein to collect it — verify with `curl http://127.0.0.1:19000/debug/log/slowlog` on the host in question if an artifact looks wrong.
- Do not average call counts/latency across time windows that straddle an app-code deploy — the query shapes and volumes can change materially between commits, exactly as this session saw when `getChairStats`, `internalGetMatching`, and the nearby-chairs query were each rewritten.

## Output Contract

Report top 6-8 routes by total time (with count/avg/p99) and top 8-10 SQL shapes by total time (with count/avg), plus any non-2xx anomalies. Do not editorialize about fixes — that's the next agent's job.
