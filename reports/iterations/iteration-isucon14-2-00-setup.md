# ISUCON14 Practice 2 — Iteration 0: Environment Setup & Baseline

## Agents Used

Sub-agents were not used because: this is infrastructure provisioning (CloudFormation, ansible,
git repo bootstrap), not a tuning hypothesis — no Profiler/App Understanding/SQL Agent inputs
are applicable until a baseline exists. This matches the AGENTS.md "Allowed Reasons To Skip
Sub-Agents" list (environment setup is not a tuning decision).

## Hypothesis

N/A — this iteration establishes the environment and measures the untouched baseline, as the
starting point for the 10-iteration improvement loop requested by the user on 2026-10-18.

## Evidence

Fresh AMI defaults (ISURIDE / isucon14), read directly from the live instance rather than any
prior project's notes:

- `webapp/go/main.go` route table (`chi` router): `/api/app/*`, `/api/owner/*`, `/api/chair/*`,
  `/api/internal/matching`.
- No pprotein/pprof integration present on the AMI; nginx access log in default `combined`
  format (no `$request_time`); MySQL slow query log commented out.
- All 7 language-stack services + `isuride-matcher`/`isuride-payment_mock`/`nginx`/`mysql`
  enabled and active on every one of the 3 fresh instances (AMI ships symmetric).

## Change

1. CloudFormation stack `isucon14-practice-2` created from
   `isucon_cf_provisioning/isucon14/cf-template-isucon14.yaml`.
2. Topology: `s1`=app+db (single host, default layout per AGENTS.md's Resource And Split
   Policy — no split without benchmark evidence), `s2`=spare, `s3`=bench+pprotein. Stopped+
   disabled `isuride-go`/`isuride-matcher`/`isuride-payment_mock`/`nginx`/`mysql` on `s2`/`s3`.
3. Ansible `general` + `pprotein` roles applied to all 3 hosts (`isucon_ansible` commit
   `d5c532f`): netdata (parent on `s3`, children on `s1`/`s2`), apt-timer disable, pprotein +
   pprotein-agent, `alp.yaml`/`targets.json` updated to ISURIDE's real routes/hosts.
4. `itohdak/isucon14_practice_2` (new private repo) initialized: captured `webapp/go`+`sql`+
   `payment_mock` source; `common/{deploy.sh,env.sh,etc/,services}` with nginx `ltsv` access log
   and MySQL `slow_query_log=1, long_query_time=0` enabled from the start; `main.go` patched to
   add `pprotein/integration/standalone` (`:8888`) and a best-effort `collectPprotein()` call
   from `postInitialize`; operator-side `scripts/{env.sh,run_cycle.sh,bench.sh,analyze.sh}`.
   Initial commit `9399531`, pushed to `main`.

## Verification

- `POST /api/initialize` with `payment_server=http://192.168.0.13:12345` (bench host's own
  built-in payment mock) — `200 {"language":"go"}`.
- pprotein group-collect triggered by the initialize hook: `webapp-s1`/`nginx-s1`/`mysql-s1`
  all `ok` (confirms pprof, httplog, and slowlog collection pipelines all work end-to-end).

## Benchmark Result

`bench run --target https://xiv.isucon.net --addr 192.168.0.11:443 --payment-bind-port 12345
--payment-url http://192.168.0.13:12345` from `s3`:

- **pass=true, score=744**
- One benchmark-internal error, type 26, count 1 — not yet investigated; at this score level
  likely a normal unsatisfied-rating-criteria count rather than a correctness bug. Flagged for
  the Profiler/App Understanding Agents to check in iteration 1 if it recurs.
- Log: `s3:/home/isucon/benchlogs/20261018-073800-baseline.log`

## pprotein Artifacts

Dashboard: `http://127.0.0.1:9000/#/group/` via `ssh pprotein` tunnel (see `~/.ssh/config`).
Collected group includes commit `9399531` (recorded automatically by pprotein from the app
host's git state) with `webapp-s1` pprof, `nginx-s1` httplog, `mysql-s1` slowlog all `ok`.

## Commit

`isucon14_practice_2@9399531` (initial state, pushed directly to `main` — environment
bootstrap, not a tuning change, so the Branch And PR Workflow does not apply to this commit).
`isucon_ansible@d5c532f` (shared infra repo, committed directly per its existing convention).

## PR

None for this iteration (environment setup, not a benchmark-backed tuning change — see Branch
And PR Workflow's scope). Tuning changes from iteration 1 onward will each go through a
feature branch + PR into `isucon14_practice_2`.

## Next Candidate

Run the Default Improvement Loop: dispatch Profiler/Resource Monitor/App Understanding/SQL
Agents in parallel against this baseline, then proceed through 10 benchmark-backed iterations
per the user's request.
