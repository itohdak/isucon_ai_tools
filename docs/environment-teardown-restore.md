# Environment Teardown & Restore

This records exactly how the `isucon14` AWS environment was torn down for cost savings during a break, and the exact steps to restore it to the state it was in at teardown time.

## State At Teardown (for reference)

- App commit deployed: `1099e7b` (`git@github.com:itohdak/isucon14_practice.git`, `main` branch).
- Last verified benchmark: `pass=true`, score in the 10000-13000 range (see `MILESTONES.md` and `reports/iterations/iteration-20260923-023402.md` for the exact last-recorded numbers).
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
   - Stop and disable the app-role services on `s3` (`isuride-go`, `isuride-matcher`, `isuride-payment_mock`, `nginx`) since it's DB-only, per `MILESTONES.md`'s DB-split notes.
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

## Cost Note

Deleting the stack removes the 3 EC2 instances, their EBS volumes (all have `DeleteOnTermination: true`), the 3 Elastic IPs, and the VPC/networking resources — all stack-owned resources, so nothing should be left behind to keep incurring cost. Verify with `aws cloudformation describe-stacks --stack-name isucon14` returning "does not exist" and `aws ec2 describe-instances` showing no `isucon14`-tagged instances in a non-terminated state after deletion completes.
