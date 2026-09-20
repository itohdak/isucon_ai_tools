import unittest

from isucon_ai_tools.agents.orchestrator import Orchestrator
from isucon_ai_tools.mcp.apm import APMMCP
from isucon_ai_tools.mcp.history import HistoryMCP
from isucon_ai_tools.skills.registry import SkillRegistry


class TestExtendedTools(unittest.TestCase):
    def test_apm_tools(self):
        mcp = APMMCP()
        self.assertEqual(mcp.get_services(host="localhost").status, "ok")
        self.assertEqual(mcp.get_slow_endpoints(host="localhost").status, "ok")

    def test_history_tools(self):
        mcp = HistoryMCP()
        self.assertEqual(mcp.list_runs().status, "ok")

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
