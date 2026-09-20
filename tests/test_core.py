import unittest

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

    def test_netdata_mcp_snapshot(self):
        mcp = NetdataMCP()
        result = mcp.get_snapshot(host="localhost", window_seconds=60)
        self.assertEqual(result.status, "ok")
        self.assertIn("points", result.data)

    def test_orchestrator_plan(self):
        orchestrator = Orchestrator()
        self.assertTrue(orchestrator.plan())


if __name__ == "__main__":
    unittest.main()
