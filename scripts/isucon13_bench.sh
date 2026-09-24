#!/bin/bash
# ISUCON13: run one bench from the operator machine on s4 and print pass/score plus the scenario counts (viewer / aggressive-streamer-moderate / viewer-spam) and the DNS attacker parallelism. IPs: see config/isucon13.yaml.
K="-i /home/itohdak/.ssh/isucon.pem -o StrictHostKeyChecking=no -o ConnectTimeout=10"
ssh $K isucon@54.95.242.1 'cd /home/isucon && sudo -u isucon ./bench run --target https://pipe.u.isucon.local --nameserver 192.168.0.13 --webapp 192.168.0.11 --enable-ssl > /tmp/bench.out 2>&1; python3 - <<PY
import json,re
r=json.load(open("/tmp/result.json"))
o=open("/tmp/bench.out").read()
def c(n):
    m=re.search(r"シナリオ "+n+r"\] (\d+) 回成功",o); return m.group(1) if m else "-"
print("pass",r.get("pass"),"score",r.get("score"),"nmsg",len(r.get("messages") or []),"viewer",c("viewer"),"aggr",c("aggressive-streamer-moderate"),"spam",c("viewer-spam"),"dns",re.search(r"並列数: (\d+)",o).group(1))
PY'
