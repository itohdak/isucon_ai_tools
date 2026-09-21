import unittest
import subprocess
import tempfile
from pathlib import Path

from isucon_ai_tools.agents.orchestrator import Orchestrator
from isucon_ai_tools.mcp.benchmark import BenchmarkMCP
from isucon_ai_tools.mcp.netdata import NetdataMCP
from isucon_ai_tools.skills.registry import SkillRegistry


class TestCore(unittest.TestCase):
    def test_registry_has_expected_skills(self):
        registry = SkillRegistry()
        self.assertIn("baseline", registry.list())
        self.assertIn("monitor", registry.list())
        self.assertIn("sql_tune", registry.list())

    def test_benchmark_mcp_runs(self):
        mcp = BenchmarkMCP()
        result = mcp.run(host="localhost", command="make bench")
        self.assertEqual(result.status, "ok")
        self.assertIn("score", result.data)

    def test_benchmark_mcp_runs_with_real_config_shape(self):
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="time=... level=INFO msg=結果 pass=true スコア=1002 種別エラー数=map[]\n",
                stderr="",
            )

        mcp = BenchmarkMCP(
            config={
                "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
                "hosts": {"bench": {"public_ip": "203.0.113.10"}},
                "benchmark": {
                    "working_directory": "/home/isucon",
                    "command": ["sudo", "-u", "isucon", "./bench", "run"],
                    "timeout_seconds": 1,
                },
            },
            runner=fake_runner,
        )
        result = mcp.run(host="bench")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["score"], 1002)
        self.assertTrue(result.data["pass"])

    def test_netdata_mcp_snapshot(self):
        mcp = NetdataMCP()
        result = mcp.get_snapshot(host="localhost", window_seconds=60)
        self.assertEqual(result.status, "ok")
        self.assertIn("points", result.data)

    def test_netdata_mcp_snapshot_with_real_config_shape(self):
        output = """UPTIME
 12:00:00 up 1 day,  1 user,  load average: 0.25, 0.50, 0.75
FREE
               total        used        free      shared  buff/cache   available
Mem:            1024         256         128           0         640         700
DF
Filesystem      Size  Used Avail Use% Mounted on
/dev/root        20G  8.0G   12G  40% /
PS
    PID COMMAND         %CPU %MEM
   1234 isuride          5.5  3.0
"""

        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=output, stderr="")

        mcp = NetdataMCP(
            config={
                "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
                "hosts": {"app": {"public_ip": "203.0.113.11"}},
            },
            runner=fake_runner,
        )
        result = mcp.get_snapshot(host="app", window_seconds=300)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["metrics"]["load_average"]["load1"], 0.25)
        self.assertEqual(result.data["metrics"]["memory"]["used_percent"], 25.0)

    def test_orchestrator_plan(self):
        orchestrator = Orchestrator()
        self.assertTrue(orchestrator.plan())

    def test_orchestrator_collects_baseline_report(self):
        slow_log = """# Query_time: 0.010000  Lock_time: 0.000000 Rows_sent: 1  Rows_examined: 10
SET timestamp=1789952074;
SELECT * FROM rides WHERE chair_id IS NULL ORDER BY created_at LIMIT 1;
"""

        resource_output = """UPTIME
 12:00:00 up 1 day,  1 user,  load average: 0.25, 0.50, 0.75
FREE
               total        used        free      shared  buff/cache   available
Mem:            1024         256         128           0         640         700
DF
Filesystem      Size  Used Avail Use% Mounted on
/dev/root        20G  8.0G   12G  40% /
PS
    PID COMMAND         %CPU %MEM
   1234 isuride          5.5  3.0
"""

        def fake_runner(command, **kwargs):
            command_text = " ".join(command) if isinstance(command, list) else str(command)
            if "./bench run" in command_text:
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout="time=... level=INFO msg=結果 pass=true スコア=1002 種別エラー数=map[]\n",
                    stderr="",
                )
            if "mysql-slow.log" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout=slow_log, stderr="")
            if "git status" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
            if "git diff" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
            if "awk" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="10 /api/chair/notification\n", stderr="")
            if "journalctl" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=resource_output, stderr="")

        config = {
            "environment": "test",
            "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
            "hosts": {
                "app": {"name": "s1", "public_ip": "203.0.113.11"},
                "bench": {"public_ip": "203.0.113.12"},
            },
            "benchmark": {
                "working_directory": "/home/isucon",
                "command": ["sudo", "-u", "isucon", "./bench", "run"],
                "timeout_seconds": 1,
            },
            "git": {"app_repo_path": "/home/isucon"},
            "mysql": {"database": "isuride"},
            "logs": {
                "mysql_slow_log": "/var/log/mysql/mysql-slow.log",
                "nginx_access_log": "/var/log/nginx/access.log",
                "app_journal_units": [],
            },
        }

        with tempfile.TemporaryDirectory() as tempdir:
            orchestrator = Orchestrator(config=config, runner=fake_runner)
            result = orchestrator.run_skill("baseline", report_dir=tempdir)
            self.assertEqual(result["result"]["status"], "ok")
            report_path = Path(result["result"]["report_path"])
            self.assertTrue(report_path.exists())
            self.assertEqual(result["result"]["report"]["benchmark"]["data"]["score"], 1002)
            self.assertIn("pprotein", result["result"]["report"])


if __name__ == "__main__":
    unittest.main()
