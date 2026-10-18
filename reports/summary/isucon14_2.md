# ISUCON14 Practice 2 — Summary

Chronological, append-only log for the `isucon14-practice-2` environment and the
`isucon14_practice_2` repository. This is an intentionally independent redo of
ISUCON14 practice (user instruction, 2026-10-18): no prior `isucon14` /
`isucon14_practice` work, reports, or `reports/summary/isucon14.md` entries
were consulted while building this environment or should be consulted for
future iterations here. Full environment facts: `config/isucon14_2.yaml`.

## 2026-10-18 — Environment built from scratch

- CloudFormation stack `isucon14-practice-2` created from
  `isucon_cf_provisioning/isucon14/cf-template-isucon14.yaml` (profile
  `isucon15.prep`, region `ap-northeast-1`) — 3x `c5.large`, private IPs fixed
  (`.11`/`.12`/`.13`), public IPs assigned at creation (see
  `config/isucon14_2.yaml`).
- Topology chosen: `s1` = app + db (default AMI single-host layout, matching
  AGENTS.md's Resource And Split Policy default — no split until benchmark
  evidence justifies one), `s2` = spare/idle, `s3` = bench + pprotein.
  `isuride-go`/`isuride-matcher`/`isuride-payment_mock`/`nginx`/`mysql`
  stopped and disabled on `s2` and `s3` (AMI ships every host symmetric with
  all services enabled by default).
- Ansible `general` (netdata + apt hygiene) and `pprotein` (alp/slp/pprotein +
  pprotein-agent) roles run against all 3 hosts. `alp.yaml`/`targets.json`
  updated to ISURIDE's actual routes/hosts (read live from
  `webapp/go/main.go` on `s1`, not from any prior project's notes);
  `targets.json` trimmed to `s1` only since `s2`/`s3` run no app.
- GitHub repo `itohdak/isucon14_practice_2` (private, created by the user)
  initialized with: captured `webapp/go` source + `sql/` + `payment_mock`
  source, `common/{deploy.sh,env.sh,etc/,services}` (nginx ltsv access log +
  MySQL slow query log enabled from the start, `long_query_time=0`),
  `webapp/go/main.go` patched to add pprotein pprof (`:8888`) and a
  best-effort `/api/group/collect` call from `postInitialize`, and operator-side
  `scripts/{env.sh,run_cycle.sh,bench.sh,analyze.sh}`. Initial commit `9399531`,
  pushed to `main`.
- Gotcha hit: `curl https://s1/...` from the operator machine hung for
  minutes before failing — `s1`/`s2`/`s3` are SSH-config aliases only (no
  local `/etc/hosts` entries; `sudo` on this operator machine requires an
  interactive password that isn't available), so plain `curl` can't resolve
  them. Fixed by using the instance's public IP with
  `--resolve xiv.isucon.net:443:<ip>` (sets both Host and TLS SNI) instead.
- Baseline verified end-to-end: `POST /api/initialize`
  (`payment_server=http://192.168.0.13:12345`, i.e. the bench host's own
  built-in payment mock, not the AMI's local `isuride-payment_mock.service`)
  then `bench run --target https://xiv.isucon.net --addr 192.168.0.11:443
  --payment-bind-port 12345 --payment-url http://192.168.0.13:12345` from `s3`.
  **Baseline: `pass=true`, score=744** (one benchmark-internal error type 26,
  not yet investigated — likely a normal unsatisfied-rating count at this
  score level, not a correctness bug). pprotein confirmed collecting
  `webapp-s1`/`nginx-s1`/`mysql-s1` (`ok`) via `POST /api/initialize`'s hook.
- `isucon_ansible` (shared infra repo, separate from `isucon14_practice_2`):
  inventory/`alp.yaml`/`targets.json`/`repo` role vars updated and committed
  directly to `master` (`d5c532f`), per this repo's existing convention for
  shared ops tooling (not the per-project PR workflow).
- GitHub auth note: `gh` CLI needed a fine-grained PAT with explicit
  "Read and Write access to code, issues, and pull requests" granted for the
  `isucon14_practice_2` repo specifically — the repo was otherwise invisible
  to `gh api`/`gh repo view` even though SSH key access worked fine.
- Next: run the AGENTS.md Default Improvement Loop (Profiler/Resource
  Monitor/App Understanding/SQL agents in parallel) starting from this
  baseline, per the user's 2026-10-18 request for 10 iterations.

## 2026-10-18 — Iteration 1: missing indexes (744 -> 3296, +343%)

- Dispatched Profiler/Resource Monitor/App Understanding/SQL Agents in
  parallel. First three converged strongly: `chairs`/`chair_locations`/
  `rides`/`ride_statuses` had zero indexes beyond PK, mysqld was CPU-bound
  (90-168% of 2 cores) during a bench run while the app itself was only
  7-23%. Added `UNIQUE(access_token)`/`INDEX(owner_id)` on `chairs`,
  `INDEX(chair_id, created_at)` on `chair_locations`,
  `INDEX(chair_id, updated_at)`/`INDEX(user_id)` on `rides`,
  `INDEX(ride_id, created_at)` on `ride_statuses`. No app code changed.
- **Incident**: `s1` went fully unresponsive (SSH + HTTPS) for ~10-15 min
  mid-iteration, very likely caused by the SQL Agent's background work
  (never returned a report after ~40 min). The `isucon15.prep` IAM user
  cannot reboot/stop instances or read CloudWatch/console output, so
  recovery required the user to reboot the instance manually from the AWS
  console. All systemd services came back automatically (enabled); no data
  or git history was lost. Added a Bash permission rule (`Bash(gh pr
  merge:*)` in `~/.claude/settings.json`, user request) after `gh pr merge`
  was blocked by the auto-mode classifier's "Merge Without Review" check,
  so subsequent iterations' PRs can be merged directly.
- Result: `pass=true`, score 744 -> **3296** (+343%), and the one baseline
  benchmark error (type 26 x1) disappeared entirely. PR #1 merged
  (https://github.com/itohdak/isucon14_practice_2/pull/1), branch deleted.
  Full detail: `reports/iterations/iteration-isucon14-2-01-missing-indexes.md`.
- Next candidate: re-run Resource Monitor Agent to see whether app CPU is
  now the limiter; `getChairStats`/`appGetNearbyChairs` N+1 patterns
  flagged by App Understanding Agent as iteration 2 candidates.
