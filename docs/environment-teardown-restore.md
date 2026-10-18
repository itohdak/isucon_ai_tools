# Environment Teardown & Restore

This records exactly how the `isucon14` AWS environment was torn down for cost savings during a break, and the exact steps to restore it to the state it was in at teardown time.

**Addendum (actual restore, 2026-09-23):** on resuming, the role mapping was changed for clarity: `s1`+`s2` became the load-targeted hosts (app, db) and `s3` became the dedicated bench/pprotein host, instead of recreating the original `s1`+`s3` load-targeted / `s2` bench arrangement described below. The steps below are otherwise accurate (same CloudFormation template, same private IPs), but wherever this doc says "db host = s3" / "bench host = s2", the actual restore put db on `s2` and bench/pprotein on `s3`. See `AGENTS.md`'s Current Environment Notes and `config/isucon14.yaml` for the current, correct mapping — this file is kept as a historical record of the teardown moment, not a live reference.

## State At Teardown (for reference)

- App commit deployed: `1099e7b` (`git@github.com:itohdak/isucon14_practice.git`, `main` branch).
- Last verified benchmark: `pass=true`, score in the 10000-13000 range (see `reports/summary/isucon14.md` and `reports/iterations/iteration-20260923-023402.md` for the exact last-recorded numbers).
- Topology: `s1` (app, private `192.168.0.11`) + `s2` (bench/pprotein, private `192.168.0.12`) + `s3` (dedicated MySQL, private `192.168.0.13`, `maxMatchesPerCall=3`).
- `s1` runs no local MySQL (stopped/disabled; `deploy.sh` restarts it anyway on every deploy, so stop it again after redeploying — see `docs/skills/implementer-agent.md`).
- CloudFormation stack `isucon14` (region `ap-northeast-1`, profile `isucon15.prep`) had `Instance1`/`Instance2`/`Instance3` + `InstanceIP1`/`InstanceIP2`/`InstanceIP3` all present — the exact deployed template is saved at `isucon_cf_provisioning/isucon14/cf-template-isucon14.yaml` (committed locally; push to GitHub failed for lack of stored credentials on the operator machine, but the commit is safe on local disk at `/home/itohdak/isucon/isucon_cf_provisioning`, which is not part of the AWS infrastructure being torn down).
- All app-level and ansible-level code is committed and pushed to GitHub (`isucon14_practice`, `isucon_ansible` — verify with `git log -1` / `git status --short` in each before assuming so, since both repos also carry some pre-existing unrelated uncommitted changes from before this session that were intentionally left alone).

**Private IPs are hardcoded in the CloudFormation template** (`192.168.0.11/12/13`) — recreating the stack from the saved template will restore the same private IPs. **Public IPs (Elastic IPs) will be different** after recreation, since EIPs are newly allocated. Update `config/isucon14.yaml`'s `public_ip` fields (and anywhere else a public IP is hardcoded, e.g. SSH commands in chat history) after restoring.

`isuride.xiv.isucon.net` did **not** resolve to this environment's app host IP even before teardown (`dig` returned an unrelated IP; `bench.xiv.isucon.net` returned nothing) — this did not block the benchmark tool, because the bench command connects directly to the private IP (`--addr 192.168.0.11:443`) and only uses the `--target` hostname for the TLS SNI/Host header, bypassing DNS entirely. If a human needs browser access to `/client` via the public hostname after restoring, that DNS may need separate attention — it was already in this state before teardown, so it is not a regression caused by the teardown itself.

## Teardown Steps (What Was Actually Done)

1. Confirmed `isucon14_practice` had no uncommitted changes (clean, pushed).
2. Saved the exact live CloudFormation template (with `Instance3` already added) to `isucon_cf_provisioning/isucon14/cf-template-isucon14.yaml` and committed it.
3. Wrote this restore runbook.
4. Deleted the stack: `aws cloudformation delete-stack --profile isucon15.prep --region ap-northeast-1 --stack-name isucon14`, then waited for `DELETE_COMPLETE`.

## Restore Steps (Do This To Resume)

1. **Recreate the stack** from the saved template:
   ```bash
   cd /home/itohdak/isucon/isucon_cf_provisioning
   aws cloudformation create-stack \
     --profile isucon15.prep --region ap-northeast-1 \
     --stack-name isucon14 \
     --template-body file://isucon14/cf-template-isucon14.yaml \
     --parameters ParameterKey=KeyPairName,ParameterValue=isucon ParameterKey=GitHubUsername,ParameterValue=itohdak
   ```
   Wait for `CREATE_COMPLETE`:
   ```bash
   aws cloudformation wait stack-create-complete --profile isucon15.prep --region ap-northeast-1 --stack-name isucon14
   ```
2. **Get the new public IPs**:
   ```bash
   aws cloudformation describe-stack-resources --profile isucon15.prep --region ap-northeast-1 --stack-name isucon14 \
     --query "StackResources[?ResourceType=='AWS::EC2::EIP'].[LogicalResourceId,PhysicalResourceId]" --output table
   ```
   `InstanceIP1` = app host (`s1`) public IP, `InstanceIP2` = bench/pprotein (`s2`), `InstanceIP3` = DB host (`s3`). Update `config/isucon14.yaml`'s `hosts.*.public_ip` fields with the new values.
3. **Wait for instance boot + SSH key provisioning** (the template's `UserData` fetches the GitHub user's SSH keys on first boot — give it ~30-60s after `CREATE_COMPLETE` before SSHing in).
4. **Set up each host's app repo checkout** (on `s1`, and originally also done once manually on `s3` for the DB setup — `s2` needs no app repo). Follow `docs/isucon-startup-checklist.md`'s "Git Management" section if starting fully fresh, or if the repo is already expected present, just `git clone`/`git pull` `git@github.com:itohdak/isucon14_practice.git` to `/home/isucon` as the `isucon` user on `s1`.
5. **Run the `general` ansible role on every host** (Netdata) — update `isucon_ansible/inventory/hosts` with the new public IPs first, then:
   ```bash
   cd /home/itohdak/isucon/isucon_ansible
   ansible-playbook playbooks/deploy_general.yaml
   ```
6. **Run the `pprotein` ansible role on every host** (pprotein server on `s2`, `pprotein-agent` on `s1` and `s3`):
   ```bash
   ansible-playbook playbooks/deploy_pprotein.yaml
   ```
7. **Set up MySQL on `s3`** (the DB host):
   - Copy `s3/etc/mysql/mysql.conf.d/mysqld.cnf` from the `isucon14_practice` repo into place on `s3` (`/etc/mysql/mysql.conf.d/mysqld.cnf`), then `sudo systemctl restart mysql`.
   - Run `webapp/sql/0-init.sql` once manually on `s3` (`sudo mysql < 0-init.sql`) to create the `isuride` database and the remote-capable `isucon`@`%` user — this is not part of the recurring `/api/initialize` flow, see `docs/skills/sql-agent.md`.
   - Stop and disable the app-role services on `s3` (`isuride-go`, `isuride-matcher`, `isuride-payment_mock`, `nginx`) since it's DB-only, per `reports/summary/isucon14.md`'s DB-split notes.
8. **Set `/home/isucon/env.sh` on `s1`**: `ISUCON_DB_HOST="192.168.0.13"` (the private IP is unchanged, so this value doesn't need to change from what's in `common/env/env.sh.redacted`, just make sure the real `env.sh` — which is gitignored — is actually created on the fresh host with this value; see `common/env/env.sh.redacted` for the full expected contents).
9. **Deploy the app to `s1`**:
   ```bash
   cd /home/isucon/common && sudo -u isucon env HOSTNAME=s1 bash ./deploy.sh
   sudo systemctl daemon-reload
   sudo systemctl restart isuride-go.service isuride-matcher.service isuride-payment_mock.service nginx.service
   sudo systemctl stop mysql.service   # deploy.sh restarts it unconditionally; s1 doesn't use local MySQL anymore
   ```
10. **Initialize and verify**:
    ```bash
    curl -sk -X POST https://isuride.xiv.isucon.net/api/initialize -H 'Content-Type: application/json' -d '{"payment_server":"http://192.168.0.12:12346"}'
    ```
    Then run a benchmark from `s2` (see `config/isucon14.yaml`'s `benchmark.command`) and confirm `pass=true` with a score in the previously-observed range before resuming tuning work.

**Known gap found on 2026-09-23 (post-restore, during later tuning work):** step 9's `deploy.sh` only builds the main `isuride` Go binary — it never builds `payment_mock`, even though `isuride-payment_mock.service`'s `ExecStart` points at a compiled `payment_mock` binary under `webapp/payment_mock/`. On the freshly-recreated `s1`, that binary didn't exist (`code=203/EXEC` on service start), and had apparently been built manually and untracked in some earlier session. Add this as an explicit step after 9: `sudo -u isucon bash -c 'cd /home/isucon/webapp/payment_mock && /home/isucon/local/golang/bin/go build -o payment_mock .'`, then restart `isuride-payment_mock.service`.

## Cost Note

Deleting the stack removes the 3 EC2 instances, their EBS volumes (all have `DeleteOnTermination: true`), the 3 Elastic IPs, and the VPC/networking resources — all stack-owned resources, so nothing should be left behind to keep incurring cost. Verify with `aws cloudformation describe-stacks --stack-name isucon14` returning "does not exist" and `aws ec2 describe-instances` showing no `isucon14`-tagged instances in a non-terminated state after deletion completes.

## ISUCON14 Practice 2 Teardown (2026-10-18)

This is the independent, from-scratch redo of ISUCON14 practice (see `AGENTS.md`'s
"Current Environment Notes — ISUCON14 Practice 2" section and `reports/summary/isucon14_2.md`)
torn down after completing the user-requested 10-iteration improvement loop. It is unrelated
to the older `isucon14` environment documented earlier in this file — do not mix the two up;
this entry does not reference or rely on that older teardown record.

### State At Teardown

- Full environment facts: `config/isucon14_2.yaml` — read that first, this is a summary.
- Final result: baseline `pass=true score=744` (commit `9399531`) -> final mean `~8257`
  (7651/8485/8635, commit merged via PR #10) — ~11.1x. Full iteration-by-iteration trail in
  `reports/summary/isucon14_2.md`.
- Topology at teardown: `s1` = app only (private `192.168.0.11`), `s2` = dedicated MySQL
  (private `192.168.0.12`, split from `s1` in iteration 7), `s3` = bench + pprotein (private
  `192.168.0.13`). Both `s1` and `s2` have a 2GB swapfile added mid-session (`/swapfile`,
  persisted in `/etc/fstab`) after repeated SSH-unresponsive incidents — not tracked in git,
  so a fresh restore from the CloudFormation template starts without it; re-add if heavy log
  analysis on these 2 vCPU hosts is needed again (or better: avoid `alp`/`slp` on live hosts
  entirely, per the lesson below).
- Git repo: `git@github.com:itohdak/isucon14_practice_2.git`, `main` branch, tip `8c6ced7`
  ("Merge pull request #10 ...") at teardown. Verified `s1`/`s2` had no uncommitted changes
  (only expected AMI-default untracked files: `.x`, `.zshrc`, `go/`) and were checked out at
  commits `c3f2333`/`565c248` respectively (each host's own last-deployed commit — both are
  ancestors of `main`'s tip, no divergent local work). `s3` never had a git checkout (bench/
  pprotein role only, no app config needed there).
- CloudFormation stack `isucon14-practice-2` (region `ap-northeast-1`, profile
  `isucon15.prep`), created from `isucon_cf_provisioning/isucon14/cf-template-isucon14.yaml`
  (unchanged from the template already in this repo — no new template saved, since nothing
  about the stack definition itself changed from the original).
- `isucon_ansible`: `inventory/hosts`, `roles/pprotein/files/{alp.yaml,targets.json}`, and
  `roles/repo/vars/main.yaml` all point at this environment (commit `d5c532f`) — will need
  repointing (or restoring from an earlier commit) before this shared repo is next used for a
  *different* project's ansible work.
- **Lesson carried forward**: running `alp`/`slp` against a live, loaded 2 vCPU/3.7GB host's
  full log file caused 4 separate total-unresponsiveness incidents this session (`s1` x2,
  `s2` x2), each requiring a manual AWS-console reboot (`isucon15.prep` cannot
  `ec2:RebootInstances`/`ec2:GetConsoleOutput`/CloudWatch itself). If this environment is
  restored, prefer `SHOW VARIABLES`/`EXPLAIN`/targeted code reading over full-log analysis
  tools while the host is under active benchmark load, and add swap immediately after
  restore (see above).

### Teardown Steps (What Was Actually Done)

1. Confirmed `isucon14_practice_2`, `isucon_ansible`, and `isucon_ai_tools` had no
   unpushed/uncommitted changes relevant to this project (one unrelated pre-existing
   uncommitted diff in `isucon_ai_tools` docs, from before this session, was left untouched).
2. Confirmed `s1`/`s2`/`s3` had no uncommitted host-side changes that would be lost.
3. Deleted the stack:
   ```bash
   aws cloudformation delete-stack --profile isucon15.prep --region ap-northeast-1 --stack-name isucon14-practice-2
   aws cloudformation wait stack-delete-complete --profile isucon15.prep --region ap-northeast-1 --stack-name isucon14-practice-2
   ```

### Restore Steps (Do This To Resume)

1. **Recreate the stack** from the existing template:
   ```bash
   cd /home/itohdak/isucon/isucon_cf_provisioning
   aws cloudformation create-stack \
     --profile isucon15.prep --region ap-northeast-1 \
     --stack-name isucon14-practice-2 \
     --template-body file://isucon14/cf-template-isucon14.yaml \
     --parameters ParameterKey=KeyPairName,ParameterValue=isucon ParameterKey=GitHubUsername,ParameterValue=itohdak
   aws cloudformation wait stack-create-complete --profile isucon15.prep --region ap-northeast-1 --stack-name isucon14-practice-2
   ```
2. **Get the new public IPs** (private IPs are fixed at `.11`/`.12`/`.13`):
   ```bash
   aws cloudformation describe-stack-resources --profile isucon15.prep --region ap-northeast-1 --stack-name isucon14-practice-2 \
     --query "StackResources[?ResourceType=='AWS::EC2::EIP'].[LogicalResourceId,PhysicalResourceId]" --output table
   ```
   Update `~/.ssh/config` (`s1`/`s2`/`s3`/`pprotein`/`bench`/`netdata*` `HostName` entries —
   this operator machine has no `/etc/hosts` backing and no passwordless `sudo`, so these
   aliases must point at IPs directly, not hostnames), `isucon_ansible/inventory/hosts`, and
   `isucon14_practice_2/scripts/env.sh`.
3. **Wait ~30-60s** after `CREATE_COMPLETE` for first-boot SSH key provisioning, then
   **disable `unattended-upgrades`** on all 3 hosts before benchmarking (it otherwise burns
   CPU for the first 30-60 min and produces misleadingly low scores):
   ```bash
   for h in s1 s2 s3; do ssh $h "sudo systemctl disable --now unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer"; done
   ```
4. **Add a 2GB swapfile on `s1` and `s2`** (not tracked in git — see the lesson above):
   ```bash
   for h in s1 s2; do ssh $h "sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab"; done
   ```
5. **Run the ansible roles** (after re-pointing `isucon_ansible/inventory/hosts` at the new
   IPs, with `s3` in the `pprotein` group, `s1` in `webapp`, `s2` in `db`):
   ```bash
   cd /home/itohdak/isucon/isucon_ansible
   ansible-playbook playbooks/deploy_general.yaml
   ansible-playbook playbooks/deploy_pprotein.yaml
   ```
6. **Set up `s1`'s git checkout and SSH key access to GitHub** (isucon_id_rsa key + config +
   gitconfig, per `docs/isucon-startup-checklist.md`'s "GitHub Push Access" section), then
   `git clone`/`checkout main` to `/home/isucon` at `8c6ced7`. Repeat the SSH-key setup on
   `s2` too (needed for its own git checkout, used only to deploy `s2/etc/mysql/...` and
   `s2/services` via `common/deploy.sh`'s per-node override convention).
7. **Set up MySQL on `s2`**: after `common/deploy.sh` copies `s2/etc/mysql/mysql.conf.d/mysqld.cnf`
   (bind-address 0.0.0.0, 2G buffer pool, etc.) and restarts `mysql`, run
   `sudo mysql -uroot < /home/isucon/webapp/sql/0-init.sql` once manually to create the
   `isuride` database and the remote-capable `isucon@'%'` user (not part of the recurring
   `/api/initialize` flow).
8. **Deploy `s1`**: `cd /home/isucon/common && bash deploy.sh` (builds `isuride`+`payment_mock`,
   stops/disables the now-redundant local mysql per `s1/disabled`, restarts
   `nginx`/`isuride-go`/`isuride-matcher`/`isuride-payment_mock`).
9. **Initialize and verify**:
   ```bash
   curl -sk --resolve xiv.isucon.net:443:<s1 public ip> -X POST https://xiv.isucon.net/api/initialize \
     -H 'Content-Type: application/json' -d '{"payment_server":"http://<s3 private ip>:12345"}'
   ```
   Then run the benchmark from `s3` (see `isucon14_practice_2/scripts/bench.sh`) and confirm
   `pass=true` with a score near the ~8257 mean recorded at teardown before resuming tuning.
