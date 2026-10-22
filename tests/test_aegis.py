"""Unit tests verifying AEGIS Core, Safety Guard, Dialogue Manager, and Orchestrator.
"""
import unittest
import asyncio
from aegis_core.safety_guard import SafetyGuard
from aegis_core.voice.dialogue_manager import DialogueManager
from aegis_core.state_manager import StateManager
from aegis_core.orchestrator import Orchestrator

class TestAEGISCore(unittest.TestCase):

    def setUp(self):
        self.safety = SafetyGuard()
        self.dialogue = DialogueManager()
        self.state = StateManager(nodes_config_path="config/nodes.json")
        self.orchestrator = Orchestrator(self.state, self.safety, self.dialogue)

    def test_safety_guard_destructive_patterns(self):
        # 1. Critical destructive commands must be gated
        res1 = self.safety.evaluate_command("rm -rf /")
        self.assertFalse(res1.is_safe)
        self.assertEqual(res1.risk_level, "CRITICAL")
        self.assertTrue(res1.requires_confirmation)

        res2 = self.safety.evaluate_command("shutdown -h now")
        self.assertTrue(res2.requires_confirmation)
        self.assertEqual(res2.risk_level, "CRITICAL")

        # 2. Benign commands should pass safely
        res3 = self.safety.evaluate_command("python -m pytest tests/")
        self.assertTrue(res3.is_safe)
        self.assertEqual(res3.risk_level, "LOW")
        self.assertFalse(res3.requires_confirmation)

    def test_dialogue_manager_multilingual_intents(self):
        # English cluster query
        p1 = self.dialogue.parse("AEGIS, tell me which DGX nodes are online and what each is doing.")
        self.assertEqual(p1["intent"], "CLUSTER_STATUS")
        self.assertEqual(p1["language"], "en")

        # Hindi / Hinglish status query
        p2 = self.dialogue.parse("Sabhi DGX nodes ka status batao.")
        self.assertEqual(p2["intent"], "CLUSTER_STATUS")
        self.assertEqual(p2["language"], "hi-en")

        # Explicit node extraction
        p3 = self.dialogue.parse("Explain the error on Node 3 and attempt a safe fix.")
        self.assertEqual(p3["intent"], "FIX_ERROR")
        self.assertEqual(p3["target_node"], "dgx-node-3")

        # Spoken Hindi response generation
        speech = self.dialogue.generate_response_text("CLUSTER_STATUS", {"online_nodes": 8, "total_nodes": 8}, lang="hi-en")
        self.assertIn("online aur ready", speech)

    def test_state_manager_node_inventory(self):
        # 8 DGX nodes should be loaded
        self.assertEqual(len(self.state.nodes), 8)
        self.assertIn("dgx-node-1", self.state.nodes)
        self.assertIn("dgx-node-8", self.state.nodes)

        # Create task
        task = self.state.create_task("Test Task", "Generate script", "dgx-node-1")
        self.assertEqual(task.status, "queued")
        self.assertEqual(self.state.nodes["dgx-node-1"].status, "busy")

    def test_orchestrator_node_selection(self):
        # Code generation routes to Node 1 (Lead Coder)
        best_code_node = self.orchestrator.select_best_node("code_generation")
        self.assertEqual(best_code_node, "dgx-node-1")

        # Vision analysis routes to Node 3 (Vision Model)
        best_vision_node = self.orchestrator.select_best_node("vision_analysis")
        self.assertEqual(best_vision_node, "dgx-node-3")

        # Explicit preferred node override
        override_node = self.orchestrator.select_best_node("code_generation", preferred_node="dgx-node-4")
        self.assertEqual(override_node, "dgx-node-4")

if __name__ == "__main__":
    unittest.main()
