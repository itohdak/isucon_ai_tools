# ISUCON Startup Checklist

This checklist records the setup normally done immediately after an ISUCON environment becomes available.

For the current Codex/agent-side architecture, see `docs/agent-architecture.md`.

## Host Aliases

Add short host aliases on the operator machine or control host.

```text
192.168.0.11 s1
192.168.0.12 s2
```

Current mapping:

- `s1`: app server, `192.168.0.11`, public IP `18.180.203.145`
- `s2`: bench server, `192.168.0.12`, public IP `13.115.244.165`

## SSH Access

Current SSH command:

```bash
ssh -i /home/itohdak/.ssh/isucon.pem ubuntu@18.180.203.145
ssh -i /home/itohdak/.ssh/isucon.pem ubuntu@13.115.244.165
```

Optional `~/.ssh/config` shape:

```sshconfig
Host s1
  HostName 18.180.203.145
  User ubuntu
  Port 22
  IdentityFile /home/itohdak/.ssh/isucon.pem

Host s2
  HostName 13.115.244.165
  User ubuntu
  Port 22
  IdentityFile /home/itohdak/.ssh/isucon.pem
```

## Hostnames

Optional, if stable hostnames are useful during operations:

```bash
sudo hostnamectl set-hostname s1
sudo sh -c 'grep -q "127.0.1.1 s1" /etc/hosts || echo "127.0.1.1 s1" >> /etc/hosts'
```

Use `s2` on the bench host.

## Pprotein Shared Observability

Use pprotein as the shared observability surface for humans and agents. Humans inspect the dashboard, while Codex records pprotein links and can trigger collection when it owns the benchmark run.

Provision a pprotein instance in the same VPC/subnet as the ISUCON servers. Use the same AMI as the ISUCON environment when possible. In the current two-host practice environment, `s2` is both the bench host and the pprotein host.

Add host aliases:

```text
<pprotein private ip> pprotein
```

Deploy pprotein and its webapp agents with Ansible:

```bash
ansible-playbook playbooks/deploy_pprotein.yaml
```

Or run the all-in-one setup when appropriate:

```bash
ansible-playbook playbooks/deploy_all.yaml
```

Verify the dashboard:

```bash
ssh -i /home/itohdak/.ssh/isucon.pem -L 9000:127.0.0.1:9000 ubuntu@13.115.244.165
```

Then open `http://127.0.0.1:9000/#/group/`.

For ISUCON14, update pprotein's `alp.yaml` matching groups to the current API list in `config/isucon14.yaml`, not the older livestream examples.

Expected collection targets:

- pprof: `http://s1:8888/debug/pprof/profile`
- httplog: `http://s1:19000/debug/log/httplog`
- slowlog: `http://s1:19000/debug/log/slowlog`

Repeat for `s2` and `s3` when those hosts run app/database roles.

## Pprotein Collection Mode

Choose the collection trigger per practice or contest run.

Current practice policy:

- Start pprotein collection from the application when bench calls `POST /api/initialize`.
- Use an initialize hook so human-run and Codex-run benchmarks follow the same observability path.
- Expect a small possible score cost from CPU profiling; human visibility is prioritized.

Manual mode:

- Humans run the official benchmark.
- Humans click pprotein collect or call `/api/group/collect` only when the initialize hook is disabled or unavailable.
- Codex reads reports/logs after the benchmark and records pprotein URLs.
- Use this as a fallback.

Agent mode:

- Codex owns the benchmark command.
- `Orchestrator.run_skill("baseline", collect_observability=True)` or `pprotein.collection.mode: agent` starts collection before benchmark execution.
- Use this only for MCP-only practice loops outside the app initialize lifecycle.

Initialize hook mode:

- The application calls pprotein collection after `/initialize`.
- This must be best-effort and must not fail initialization if pprotein is down.
- Keep this behind a config/env flag so it can be disabled quickly.
- This is the current default in `config/isucon14.yaml`.

Example Go hook:

```go
go func() {
    if _, err := http.Get("http://s2:9000/api/group/collect"); err != nil {
        log.Printf("failed to communicate with pprotein: %v", err)
    }
}()
```

Recommended default:

- Use initialize hook mode for Codex-driven and human-driven practice.
- Use manual mode only as a fallback.
- Keep agent mode only for MCP-only practice runs that do not go through `/initialize`.

## Pprof

Enable pprof for Go applications when pprotein should collect CPU profiles.

Add the pprotein standalone integration:

```go
import "github.com/kaz/pprotein/integration/standalone"
```

Start it from `main()`:

```go
go standalone.Integrate(":8888")
```

Verify:

```bash
curl http://localhost:8888/debug/pprof/
```

## Netdata Port Forwarding

If netdata is installed, use SSH local forwarding through the pprotein host.

```sshconfig
Host netdata
  HostName pprotein
  User isucon
  Port 22
  IdentityFile /home/itohdak/.ssh/isucon_id_rsa
  LocalForward 19991 192.168.0.11:19999
  LocalForward 19992 192.168.0.12:19999
  LocalForward 19993 192.168.0.13:19999
```

Start the tunnel:

```bash
ssh netdata -fN
```

Open:

- `http://localhost:19991`
- `http://localhost:19992`
- `http://localhost:19993`

## Benchmark-Time Resource Monitoring

Resource metrics must be collected during benchmark runs before considering web/app/db instance separation.

Default rule:

- Do not split web/app/db only because extra servers are available.
- Split only when CPU, memory, disk IO, or network metrics during bench show a bottleneck that the split should relieve.
- If CPU idle remains high, prioritize API/SQL/application behavior before instance separation.

Use Netdata when installed. Otherwise sample with:

```bash
vmstat 1
pidstat -durh 1
mpstat -P ALL 1
iostat -xz 1
```

Record the before/after resource evidence in the iteration report if an instance split is proposed or attempted.

See also:

- `docs/resource-scaling-policy.md`
- `docs/mysql-operations-tips.md`
- `http://localhost:19992`
- `http://localhost:19993`

## Source And Config Capture

Before tuning, capture the initial application and runtime configuration into version control.

Important paths on the current app host:

- App: `/home/isucon/webapp`
- Environment: `/home/isucon/env.sh`
- Nginx: `/etc/nginx/nginx.conf`, `/etc/nginx/sites-enabled/isuride.conf`
- MySQL: `/etc/mysql/mysql.conf.d/mysqld.cnf`
- Systemd: `/etc/systemd/system/isuride-go.service`, `isuride-matcher.service`, `isuride-payment_mock.service`

Do not commit secrets. Redact credentials before storing copied config in this repository.

## Git Management

Use git as the safety net for every benchmark iteration.

Repository policy:

- Create the contest repository from `https://github.com/itohdak/isucon_template`.
- Set that repository as `origin` on the app host.
- Keep shared files under `common`.
- Keep per-server overrides under `s1`, `s2`, and `s3`.
- Put files in `s1` / `s2` / `s3` with the same relative path as `common` when a server needs different config.

Recommended initial flow on the app host:

```bash
cd /home/isucon
git init
git checkout -b main
git status
```

If using a remote repository:

```bash
git remote add origin <repository-url>
git fetch --all
git merge origin/main
```

## GitHub Push Access

Use a dedicated SSH key for contest repositories so app hosts can push commits during tuning.

Prepare the operator machine:

```bash
test -f ~/.ssh/isucon_id_rsa
test -f ~/.ssh/isucon_id_rsa.pub
```

Register `~/.ssh/isucon_id_rsa.pub` in GitHub before the contest or setup run. Prefer a repository deploy key with write access for the contest repository. An account-level SSH key also works, but has a wider blast radius.

On each app host, install the key and git settings for the `isucon` user:

```bash
sudo install -d -o isucon -g isucon -m 700 /home/isucon/.ssh
sudo install -o isucon -g isucon -m 600 /tmp/isucon_id_rsa /home/isucon/.ssh/id_rsa
sudo install -o isucon -g isucon -m 644 /tmp/isucon_id_rsa.pub /home/isucon/.ssh/id_rsa.pub
sudo install -o isucon -g isucon -m 600 /tmp/config /home/isucon/.ssh/config
sudo install -o isucon -g isucon -m 600 /tmp/.gitconfig /home/isucon/.gitconfig
```

Expected `/home/isucon/.gitconfig`:

```gitconfig
[user]
        email = itohdak@gmail.com
        name = itohdak
[url "git@github.com:"]
        insteadOf = https://github.com/
```

Expected `/home/isucon/.ssh/config`:

```sshconfig
Host github.com
  StrictHostKeyChecking no
```

Verify GitHub access as the `isucon` user:

```bash
sudo -u isucon ssh -T git@github.com
```

If this returns `Permission denied (publickey)`, the host-side setup is present but the public key is not registered or does not have write access to the GitHub repository.

Set or update the remote:

```bash
cd /home/isucon
git remote add origin https://github.com/itohdak/<repo-name>.git || git remote set-url origin https://github.com/itohdak/<repo-name>.git
git push -u origin main
```

Do not commit private keys. Remove temporary transfer copies from `/tmp` after installation.

Capture application source and redacted runtime configuration:

```bash
mkdir -p common/env common/etc/nginx common/etc/mysql/mysql.conf.d common/etc/systemd/system
mkdir -p s1/etc s2/etc s3/etc

cp -p /etc/nginx/nginx.conf common/etc/nginx/nginx.conf
cp -p /etc/nginx/sites-enabled/isuride.conf common/etc/nginx/isuride.conf
cp -p /etc/mysql/mysql.conf.d/mysqld.cnf common/etc/mysql/mysql.conf.d/mysqld.cnf
cp -p /etc/systemd/system/isuride-go.service common/etc/systemd/system/isuride-go.service
cp -p /etc/systemd/system/isuride-matcher.service common/etc/systemd/system/isuride-matcher.service
cp -p /etc/systemd/system/isuride-payment_mock.service common/etc/systemd/system/isuride-payment_mock.service
```

When a config differs by server, copy it to the matching host directory instead of changing `common`.

Example:

```bash
mkdir -p s1/etc/nginx
cp -p /etc/nginx/sites-enabled/isuride.conf s1/etc/nginx/isuride.conf
```

Handle `/home/isucon/env.sh` carefully because it may contain secrets.

```bash
cp -p /home/isucon/env.sh common/env/env.sh.redacted
vi common/env/env.sh.redacted
```

Commit the initial state before any tuning:

```bash
git status
git add .
git commit -m "initial state"
```

Iteration rule:

- Commit once after the initial environment setup.
- Before each hypothesis, confirm `git status` is clean or intentionally understood.
- Make one logical change per benchmark.
- Commit only if the benchmark improves and the app remains valid.
- Revert or restore changes that regress score or correctness.

Before each benchmark:

- Deploy the selected branch.
- Apply configuration files.
- Rebuild the app.
- Restart app, nginx, and database services if the deploy flow requires it.
- Rotate or mark logs so the next report can be attributed to the current run.
- Start pprotein collection manually or via agent mode, depending on the selected collection mode.

Past Ansible flow:

```bash
ansible-playbook playbooks/deploy_repo.yaml --extra-vars "branch=<branch name>"
```

Useful commands:

```bash
git status --short
git diff
git diff --stat
git restore <path>
git log --oneline --decorate -n 10
```

Do not commit:

- Raw secrets from `/home/isucon/env.sh`
- Private keys
- Large generated logs
- Build artifacts that can be regenerated
- `__pycache__`, `.pytest_cache`, Go build cache, Node package caches

## Nginx Access Log For API Aggregation

Enable an access log format that `alp` or similar tooling can aggregate by route.

Recommended LTSV format:

```nginx
log_format ltsv "time:$time_local"
  "\thost:$remote_addr"
  "\tforwardedfor:$http_x_forwarded_for"
  "\treq:$request"
  "\tmethod:$request_method"
  "\turi:$request_uri"
  "\tstatus:$status"
  "\tsize:$body_bytes_sent"
  "\treferer:$http_referer"
  "\tua:$http_user_agent"
  "\treqtime:$request_time"
  "\truntime:$upstream_http_x_runtime"
  "\tapptime:$upstream_response_time"
  "\tcache:$upstream_http_x_cache"
  "\tvhost:$host";

access_log /var/log/nginx/access.log ltsv;
```

Verification:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo tail -n 5 /var/log/nginx/access.log
```

Current target log path:

- `/var/log/nginx/access.log`

## MySQL Slow Query Log

Enable slow query logging for all queries during investigation.

For MySQL, edit:

```text
/etc/mysql/mysql.conf.d/mysqld.cnf
```

Recommended settings:

```ini
slow_query_log = 1
slow_query_log_file = /var/log/mysql/mysql-slow.log
long_query_time = 0.0
```

Verification:

```bash
sudo systemctl restart mysql
sudo mysql -N -e "SHOW VARIABLES LIKE 'slow_query_log'; SHOW VARIABLES LIKE 'slow_query_log_file'; SHOW VARIABLES LIKE 'long_query_time';"
sudo ls -l /var/log/mysql/mysql-slow.log
```

Current database:

- MySQL `8.0.46-0ubuntu0.24.04.3`
- Database `isuride`
- Access method: `sudo mysql` on the app host

## API Matching Groups

If using `alp` or pprotein, configure route grouping before comparing benchmark runs.

For ISUCON14, start with route groups such as:

```yaml
matching_groups:
  - ^/api/app/users$
  - ^/api/app/payment-methods$
  - ^/api/app/nearby-chairs$
  - ^/api/app/rides$
  - ^/api/app/rides/estimated-fare$
  - ^/api/app/rides/[^/]+/evaluation$
  - ^/api/app/notification$
  - ^/api/chair/chairs$
  - ^/api/chair/activity$
  - ^/api/chair/coordinate$
  - ^/api/chair/rides/[^/]+/status$
  - ^/api/chair/notification$
  - ^/api/owner/owners$
  - ^/api/owner/chairs$
  - ^/api/owner/chairs/[^/]+$
  - ^/api/owner/sales$
  - ^/api/internal/matching$
```

Refine these once actual access logs show high-cardinality paths.

## Benchmark Command

Use the non-default payment bind port because the bench host also runs the AMI's `payment_mock` on `:12345`.

```bash
cd /home/isucon
sudo -u isucon ./bench run \
  --target https://bench.xiv.isucon.net \
  --addr 192.168.0.11:443 \
  --payment-bind-port 12346 \
  --payment-url http://192.168.0.12:12346
```

Current confirmed baseline:

- `pass=true`
- score `1002`
- measured on `2026-09-21`
