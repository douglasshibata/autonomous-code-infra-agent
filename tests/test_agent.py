import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.security import SecurityGuardrails
from core.self_healing import SelfHealingEngine
from core.orchestrator import AgentOrchestrator
from playbooks.network_vpn_check import run_diagnostics
from playbooks.figma_sipaf_sync import sync_sipaf_assets
from playbooks.discord_status_report import generate_and_send_status_report

class TestAutonomousAgent(unittest.TestCase):

    def setUp(self):
        self.config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../config'))
        self.security_cfg = os.path.join(self.config_dir, 'security_guardrails.json')
        self.yaml_cfg = os.path.join(self.config_dir, 'open_interpreter_config.yaml')

    def test_security_guardrails_command_validation(self):
        security = SecurityGuardrails(config_path=self.security_cfg)

        # Test dangerous commands
        is_safe, reason = security.validate_command("rm -rf /")
        self.assertFalse(is_safe)
        self.assertIn("Security Violation", reason)

        is_safe_chmod, _ = security.validate_command("chmod -R 777 /var/log")
        self.assertFalse(is_safe_chmod)

        # Test safe commands
        is_safe_ls, _ = security.validate_command("python3 playbooks/network_vpn_check.py")
        self.assertTrue(is_safe_ls)

    def test_security_guardrails_secret_masking(self):
        security = SecurityGuardrails(config_path=self.security_cfg)

        # Test masking
        os.environ["FIGMA_TOKEN"] = "secret_figma_token_12345"
        output_text = "Connecting to Figma with token secret_figma_token_12345"
        sanitized = security.sanitize_output(output_text)
        self.assertNotIn("secret_figma_token_12345", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)

    def test_self_healing_error_classification(self):
        engine = SelfHealingEngine()

        # Test Missing Package
        stderr_mod = "ModuleNotFoundError: No module named 'requests'"
        classified = engine.classify_error(stderr_mod)
        self.assertEqual(classified["category"], "MISSING_DEPENDENCY")
        self.assertEqual(classified["package"], "requests")
        self.assertEqual(classified["fix_command"], "pip install requests")

        # Test Network Timeout
        stderr_net = "urllib3.exceptions.ReadTimeoutError: HTTPSConnectionPool Read timed out."
        classified_net = engine.classify_error(stderr_net)
        self.assertEqual(classified_net["category"], "NETWORK_TIMEOUT")

    def test_self_healing_execution_success(self):
        engine = SelfHealingEngine(max_retries=2)
        mock_fn = MagicMock(return_value=(0, "Success output", ""))

        res = engine.execute_with_self_healing(mock_fn)
        self.assertTrue(res["success"])
        self.assertEqual(res["attempts"], 1)

    def test_orchestrator_playbook_execution(self):
        orchestrator = AgentOrchestrator(config_path=self.yaml_cfg)
        playbook_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../playbooks/network_vpn_check.py'))

        res = orchestrator.execute_playbook(playbook_path)
        self.assertTrue(res["success"])
        self.assertIn("stdout", res)

    def test_playbook_network_vpn_check(self):
        report = run_diagnostics()
        self.assertEqual(report["playbook"], "network_vpn_check")
        self.assertIn("overall_status", report)
        self.assertEqual(len(report["endpoints"]), 3)

    def test_playbook_figma_sipaf_sync(self):
        manifest = sync_sipaf_assets()
        self.assertEqual(manifest["project"], "SIPAF - Sistema de Inscrição e Planejamento")
        self.assertGreater(len(manifest["downloaded_assets"]), 0)

    def test_playbook_discord_status_report(self):
        report = generate_and_send_status_report()
        self.assertIn("embeds", report["payload"])
        self.assertEqual(report["payload"]["username"], "Agente Autônomo de Infraestrutura")

if __name__ == "__main__":
    unittest.main()
