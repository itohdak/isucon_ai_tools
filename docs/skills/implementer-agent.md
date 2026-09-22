# Implementer Agent Skill

Apply one selected, minimal, already-approved change. File ownership must be assigned before starting (see `AGENTS.md`'s Ownership Rules). Build and lint locally before deploying.

## Local Build

```bash
cd webapp/go && GOCACHE=/tmp/go-build-cache go build ./... && GOCACHE=/tmp/go-build-cache go vet ./...
gofmt -l . && gofmt -w <any-listed-file>   # gofmt -l lists files that need formatting
```

## Deploy Gotchas (Learned The Hard Way This Session)

`common/deploy.sh` copies `common/etc/**` into place, then rebuilds the Go binary and restarts services. Three real gotchas:

1. **Per-server overrides never apply with a plain invocation.** `deploy.sh` checks `../${HOSTNAME}/...` to find per-host override files (`s1/etc/...`, `s3/etc/...`), but `$HOSTNAME` is the shell's real machine hostname (e.g. `ip-192-168-0-11`), not the repo's logical `s1`/`s2`/`s3` names — so the override silently never matches unless you set it explicitly:
   ```bash
   sudo -u isucon env HOSTNAME=s1 bash ./deploy.sh   # substitute s2/s3 as appropriate
   ```
   Do this whenever `s1/etc/...`, `s2/etc/...`, or `s3/etc/...` has a file relevant to the host you're deploying to. `deploy.sh` itself has not been changed to fix this (changing deploy scripts needs separate human approval per `AGENTS.md`), so keep using the `HOSTNAME=` workaround.
2. **`deploy.sh` never runs `systemctl daemon-reload`.** If you changed a systemd unit file (via `common/etc/systemd/system/*.service` or a per-server override), you must run `sudo systemctl daemon-reload` yourself before restarting the affected service, or the old unit definition stays active.
3. **`deploy.sh` unconditionally runs `sudo systemctl restart mysql`,** regardless of host. On `s1` (post DB-split, where MySQL is stopped/disabled) this silently starts a now-unused local MySQL on every deploy. Stop it again afterward if resource cleanliness matters for the next benchmark: `sudo systemctl stop mysql.service`.

## Change Size Discipline

Matching-adjacent and throughput-adjacent changes are the highest-risk area in this codebase (see the App Understanding Agent skill). This session's clearest lesson: a 20x jump in matcher batch size caused a catastrophic overload that a 3x step did not. **Prefer the smallest change that tests the hypothesis, especially for anything touching `internalGetMatching`, notification delivery, or per-tick/per-poll rate limits** — implement, benchmark, and only then consider a further incremental step, rather than implementing the "final" aggressive version up front.

## Schema Changes

New columns on an existing table must go through a post-seed `ALTER TABLE` in `webapp/sql/init.sh`, not directly in `1-schema.sql`'s `CREATE TABLE` — see the SQL Agent skill for why (`3-initial-data.sql.gz` uses positional `INSERT`s tied to the original column layout).

## After Implementing

List every changed file explicitly in your final answer. Do not deploy or run destructive commands yourself unless the loop has already delegated that — implementation and verification are separate roles per `AGENTS.md`'s Default Improvement Loop, even when Codex ends up doing both directly.
