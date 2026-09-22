import unittest
import subprocess
import tempfile
from pathlib import Path

from isucon_ai_tools.agents.orchestrator import Orchestrator
from isucon_ai_tools.mcp.apm import APMMCP
from isucon_ai_tools.mcp.deploy import DeployMCP
from isucon_ai_tools.mcp.filesystem import FilesystemMCP
from isucon_ai_tools.mcp.git import GitMCP
from isucon_ai_tools.mcp.history import HistoryMCP
from isucon_ai_tools.mcp.iteration import IterationMCP
from isucon_ai_tools.mcp.logs import LogsMCP
from isucon_ai_tools.mcp.mysql import MySQLMCP
from isucon_ai_tools.mcp.pprotein import PproteinMCP
from isucon_ai_tools.mcp.shell import ShellMCP
from isucon_ai_tools.policies.guardrails import Guardrails
from isucon_ai_tools.skills.registry import SkillRegistry


class TestExtendedTools(unittest.TestCase):
    def test_apm_tools(self):
        mcp = APMMCP()
        self.assertEqual(mcp.get_services(host="localhost").status, "ok")
        self.assertEqual(mcp.get_slow_endpoints(host="localhost").status, "ok")

    def test_history_tools(self):
        mcp = HistoryMCP()
        self.assertEqual(mcp.list_runs().status, "ok")

    def test_history_persists_runs_and_markdown_report(self):
        with tempfile.TemporaryDirectory() as tempdir:
            storage_path = Path(tempdir) / "history.jsonl"
            report_dir = Path(tempdir) / "history"
            mcp = HistoryMCP(storage_path=str(storage_path), report_dir=str(report_dir))

            result = mcp.record_run(
                run_id="run-001",
                before_score=673,
                after_score=1297,
                hypothesis="Add ride_statuses indexes",
                changed_files=["webapp/sql/1-schema.sql"],
                evidence={"top_query": "SELECT status FROM ride_statuses WHERE ride_id = ?"},
                rollback_status="not_needed",
                before_report="reports/before.json",
                after_report="reports/after.json",
                commit="b1bfb60",
            )
            self.assertEqual(result.status, "ok")
            self.assertTrue(storage_path.exists())
            self.assertTrue(Path(result.data["markdown_path"]).exists())

            listed = HistoryMCP(storage_path=str(storage_path), report_dir=str(report_dir)).list_runs()
            self.assertEqual(listed.status, "ok")
            self.assertEqual(len(listed.data["runs"]), 1)
            self.assertEqual(listed.data["runs"][0]["delta"], 624)

            summary = mcp.generate_summary()
            self.assertEqual(summary.data["run_count"], 1)
            self.assertEqual(summary.data["total_delta"], 624)

    def test_iteration_compares_reports_and_suggests_next_action(self):
        before = {
            "benchmark": {"data": {"score": 673, "error_counts": "map[26:1]"}},
            "mysql": {
                "slow_queries": {
                    "data": {
                        "slow_queries": [
                            {"query": "SELECT status FROM ride_statuses WHERE ride_id = ?", "count": 5, "total_time_ms": 100.0}
                        ]
                    }
                }
            },
            "logs": {"routes": {"data": {"routes": [{"uri": "/api/chair/notification", "count": 10}]}}},
            "resources": {"data": {"metrics": {"load_average": {"load1": 1.0}}}},
        }
        after = {
            "benchmark": {"data": {"score": 1297, "error_counts": "map[]"}},
            "mysql": {
                "slow_queries": {
                    "data": {
                        "slow_queries": [
                            {"query": "SELECT * FROM rides WHERE chair_id = ? ORDER BY updated_at DESC", "count": 2, "total_time_ms": 20.0}
                        ]
                    }
                }
            },
            "logs": {"routes": {"data": {"routes": [{"uri": "/api/chair/notification", "count": 20}]}}},
            "resources": {"data": {"metrics": {"load_average": {"load1": 3.0}}}},
        }

        with tempfile.TemporaryDirectory() as tempdir:
            before_path = Path(tempdir) / "before.json"
            after_path = Path(tempdir) / "after.json"
            before_path.write_text(json_dumps(before))
            after_path.write_text(json_dumps(after))

            result = IterationMCP().compare_reports(str(before_path), str(after_path), output_dir=tempdir)

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.data["score"]["delta"], 624)
            self.assertEqual(result.data["errors"]["resolved"], ["26"])
            self.assertTrue(Path(result.data["markdown_path"]).exists())
            self.assertEqual(result.data["suggestions"][0]["area"], "slow_query")

    def test_pprotein_skips_collection_in_manual_mode(self):
        mcp = PproteinMCP(
            config={
                "pprotein": {
                    "enabled": True,
                    "base_url": "http://pprotein:9000",
                    "collection": {"mode": "manual"},
                }
            }
        )
        result = mcp.collect()
        self.assertEqual(result.status, "skipped")
        self.assertIn("manual", result.message)

    def test_pprotein_collects_when_forced(self):
        def fake_http_get(url, timeout_seconds):
            return {"status_code": 200, "body": "ok"}

        mcp = PproteinMCP(
            config={
                "pprotein": {
                    "enabled": True,
                    "base_url": "http://pprotein:9000",
                    "collection": {"mode": "manual", "collect_endpoint": "/api/group/collect"},
                }
            },
            http_get=fake_http_get,
        )
        result = mcp.collect(force=True)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["url"], "http://pprotein:9000/api/group/collect")

    def test_pprotein_collects_in_agent_mode(self):
        calls = []

        def fake_http_get(url, timeout_seconds):
            calls.append((url, timeout_seconds))
            return {"status_code": 200, "body": "ok"}

        mcp = PproteinMCP(
            config={
                "pprotein": {
                    "enabled": True,
                    "base_url": "http://pprotein:9000",
                    "collection": {
                        "mode": "agent",
                        "collect_endpoint": "/api/group/collect",
                        "timeout_seconds": 90,
                    },
                }
            },
            http_get=fake_http_get,
        )
        result = mcp.collect()
        self.assertEqual(result.status, "ok")
        self.assertEqual(calls, [("http://pprotein:9000/api/group/collect", 90)])

    def test_mysql_slow_queries_with_real_config_shape(self):
        slow_log = """# Query_time: 0.010000  Lock_time: 0.000000 Rows_sent: 1  Rows_examined: 10
SET timestamp=1789952074;
SELECT * FROM rides WHERE chair_id IS NULL ORDER BY created_at LIMIT 1;
# Query_time: 0.020000  Lock_time: 0.000000 Rows_sent: 1  Rows_examined: 10
SET timestamp=1789952075;
SELECT * FROM rides WHERE chair_id IS NULL ORDER BY created_at LIMIT 1;
"""

        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=slow_log, stderr="")

        mcp = MySQLMCP(
            config={
                "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
                "hosts": {"app": {"public_ip": "203.0.113.11"}},
                "mysql": {"database": "isuride"},
                "logs": {"mysql_slow_log": "/var/log/mysql/mysql-slow.log"},
            },
            runner=fake_runner,
        )
        result = mcp.get_slow_queries(host="app", limit=1)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["slow_queries"][0]["count"], 2)
        self.assertEqual(result.data["slow_queries"][0]["total_time_ms"], 30.0)

    def test_mysql_attributed_slow_queries_groups_by_api_and_query(self):
        slow_log = """# Query_time: 0.010000  Lock_time: 0.000000 Rows_sent: 1  Rows_examined: 10
SET timestamp=1789952074;
/* api:chairGetNotification route:GET /api/chair/notification */
SELECT * FROM rides WHERE chair_id = 'chair-1' ORDER BY updated_at DESC LIMIT 1;
# Query_time: 0.020000  Lock_time: 0.000000 Rows_sent: 1  Rows_examined: 10
SET timestamp=1789952075;
/* api:chairGetNotification route:GET /api/chair/notification */
SELECT * FROM rides WHERE chair_id = 'chair-2' ORDER BY updated_at DESC LIMIT 1;
# Query_time: 0.030000  Lock_time: 0.000000 Rows_sent: 1  Rows_examined: 10
SET timestamp=1789952076;
/* fn:getLatestRideStatus */
SELECT status FROM ride_statuses WHERE ride_id = 'ride-1' ORDER BY created_at DESC LIMIT 1;
# Query_time: 0.040000  Lock_time: 0.000000 Rows_sent: 1  Rows_examined: 10
SET timestamp=1789952077;
/* api:ownerGetSales route:GET /api/owner/sales */ SELECT * FROM chairs WHERE owner_id = 'owner-1';
"""
        rows = MySQLMCP()._parse_attributed_slow_log(slow_log, limit=10)

        self.assertEqual(rows[0]["api"], "GET /api/owner/sales")
        self.assertEqual(rows[0]["total_time_ms"], 40.0)
        notification = next(row for row in rows if row["api"] == "GET /api/chair/notification")
        self.assertEqual(notification["count"], 2)
        self.assertEqual(notification["total_time_ms"], 30.0)
        self.assertIn("chair_id = ?", notification["query"])
        latest_status = next(row for row in rows if row["fn"] == "getLatestRideStatus")
        self.assertEqual(latest_status["api"], "unknown")
        self.assertEqual(latest_status["total_time_ms"], 30.0)

    def test_logs_route_summary_with_real_config_shape(self):
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="12.500000 10 1.250000 2.000000 /api/chair/notification\n1.200000 3 0.400000 0.500000 /api/app/rides\n",
                stderr="",
            )

        mcp = LogsMCP(
            config={
                "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
                "hosts": {"app": {"public_ip": "203.0.113.11"}},
                "logs": {"nginx_access_log": "/var/log/nginx/access.log", "app_journal_units": []},
            },
            runner=fake_runner,
        )
        result = mcp.summarize_routes(host="app", limit=2)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["routes"][0]["uri"], "/api/chair/notification")
        self.assertEqual(result.data["routes"][0]["total_time_seconds"], 12.5)
        self.assertEqual(result.data["sort"], "total_time_seconds")

    def test_git_status_with_real_config_shape(self):
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=" M webapp/go/main.go\n", stderr="")

        mcp = GitMCP(
            config={
                "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
                "hosts": {"app": {"public_ip": "203.0.113.11"}},
                "git": {"app_repo_path": "/home/isucon"},
            },
            runner=fake_runner,
        )
        result = mcp.status(repo_path="/home/isucon")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["status"], [" M webapp/go/main.go"])

    def test_guardrails_path_prefix_is_boundary_aware(self):
        guardrails = Guardrails(allowlist_paths=["/home/isucon"])
        self.assertTrue(guardrails.is_allowed_path("/home/isucon/webapp/main.go"))
        self.assertFalse(guardrails.is_allowed_path("/home/isucon2/webapp/main.go"))

    def test_filesystem_write_rejects_outside_allowlist(self):
        guardrails = Guardrails(allowlist_paths=["/tmp/isucon-allowed"])
        mcp = FilesystemMCP(guardrails=guardrails)
        result = mcp.write_file("/tmp/isucon-denied/file.txt", "nope")
        self.assertEqual(result.status, "error")
        self.assertIn("outside allowlist", result.message)

    def test_filesystem_write_creates_backup_before_overwrite(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "settings.conf"
            path.write_text("old")
            guardrails = Guardrails(allowlist_paths=[tempdir], require_backup_before_write=True)
            mcp = FilesystemMCP(guardrails=guardrails)

            result = mcp.write_file(str(path), "new")

            self.assertEqual(result.status, "ok")
            self.assertEqual(path.read_text(), "new")
            self.assertEqual(Path(result.data["backup_path"]).read_text(), "old")

    def test_git_restore_rejects_parent_traversal_paths(self):
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        mcp = GitMCP(
            config={
                "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
                "hosts": {"app": {"public_ip": "203.0.113.11"}},
                "git": {"app_repo_path": "/home/isucon"},
            },
            runner=fake_runner,
            guardrails=Guardrails(allowlist_paths=["/home/isucon"]),
        )
        result = mcp.restore(repo_path="/home/isucon", paths=["../env.sh"])
        self.assertEqual(result.status, "error")
        self.assertIn("repo-relative", result.message)

    def test_shell_mcp_rejects_denied_command(self):
        mcp = ShellMCP(guardrails=Guardrails(allowlist_paths=["/tmp"]))
        result = mcp.run("rm -rf /", cwd="/tmp")
        self.assertEqual(result.status, "error")
        self.assertIn("denied", result.message)

    def test_shell_mcp_runs_allowed_command(self):
        def fake_runner(command, **kwargs):
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok\n", stderr="")

        mcp = ShellMCP(runner=fake_runner, guardrails=Guardrails(allowlist_paths=["/tmp"]))
        result = mcp.run("printf ok", cwd="/tmp")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["stdout"], "ok\n")

    def test_deploy_mcp_rejects_dirty_worktree_by_default(self):
        def fake_runner(command, **kwargs):
            command_text = " ".join(command)
            if "git status --short" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout=" M webapp/go/main.go\n", stderr="")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        mcp = DeployMCP(config=self._deploy_config(), runner=fake_runner, guardrails=Guardrails(allowlist_paths=["/home/isucon"]))
        result = mcp.deploy()
        self.assertEqual(result.status, "error")
        self.assertIn("clean git working tree", result.message)

    def test_deploy_mcp_runs_deploy_and_health_check(self):
        seen_commands = []

        def fake_runner(command, **kwargs):
            command_text = " ".join(command)
            seen_commands.append(command_text)
            if "git status --short" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
            if "test -x" in command_text or "bash -n" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
            if "deploy.sh" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="deployed\n", stderr="")
            if "systemctl is-active" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="active\nactive\n", stderr="")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        config = self._deploy_config()
        config["deploy"] = {
            "command": "cd /home/isucon/common && sudo -u isucon bash ./deploy.sh",
            "health_services": ["isuride-go.service", "nginx.service"],
        }
        mcp = DeployMCP(config=config, runner=fake_runner, guardrails=Guardrails(allowlist_paths=["/home/isucon"]))
        result = mcp.deploy()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["health"]["services"][0]["state"], "active")
        self.assertTrue(any("deploy.sh" in command for command in seen_commands))

    def test_deploy_mcp_dry_run_runs_preflight_only(self):
        seen_commands = []

        def fake_runner(command, **kwargs):
            command_text = " ".join(command)
            seen_commands.append(command_text)
            if "git status --short" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
            if "test -x" in command_text or "bash -n" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
            if "systemctl is-active" in command_text:
                return subprocess.CompletedProcess(args=command, returncode=0, stdout="active\nactive\n", stderr="")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        config = self._deploy_config()
        config["deploy"] = {
            "command": "cd /home/isucon/common && sudo -u isucon bash ./deploy.sh",
            "health_services": ["isuride-go.service", "nginx.service"],
        }
        mcp = DeployMCP(config=config, runner=fake_runner, guardrails=Guardrails(allowlist_paths=["/home/isucon"]))
        result = mcp.deploy(dry_run=True)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.data["dry_run"])
        self.assertFalse(any("cd /home/isucon/common" in command for command in seen_commands))

    def test_orchestrator_plan_includes_deploy(self):
        self.assertIn("deploy", Orchestrator().plan())

    def test_orchestrator_plan_includes_analyze_iteration(self):
        self.assertIn("analyze_iteration", Orchestrator().plan())

    def _deploy_config(self):
        return {
            "ssh": {"user": "ubuntu", "private_key_path": "/tmp/key.pem"},
            "hosts": {"app": {"public_ip": "203.0.113.11"}},
            "git": {"app_repo_path": "/home/isucon"},
            "services": {"app": ["isuride-go.service", "nginx.service"]},
        }


def json_dumps(value):
    import json

    return json.dumps(value, ensure_ascii=False)

    def test_registry_includes_trace_and_history_skills(self):
        registry = SkillRegistry()
        self.assertIn("trace_analysis", registry.list())
        self.assertIn("record_improvement", registry.list())

    def test_orchestrator_handles_extended_skills(self):
        orchestrator = Orchestrator()
        self.assertIn("trace_analysis", orchestrator.plan())
        self.assertIn("record_improvement", orchestrator.plan())


if __name__ == "__main__":
    unittest.main()
