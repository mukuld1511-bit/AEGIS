import unittest
from fastapi.testclient import TestClient

from aegis_core.state_manager import StateManager
from aegis_core.safety_guard import SafetyGuard
from aegis_core.voice.dialogue_manager import DialogueManager
from aegis_core.orchestrator import Orchestrator
from aegis_core.api.server import create_app

class TestSixNodePipeline(unittest.TestCase):
    def setUp(self):
        self.state_mgr = StateManager("config/nodes.json")
        self.safety = SafetyGuard()
        self.dialogue = DialogueManager()
        self.orchestrator = Orchestrator(self.state_mgr, self.safety, self.dialogue)
        self.app = create_app(self.state_mgr, self.orchestrator, self.safety)
        self.client = TestClient(self.app)

    def test_custom_chain_opencv_node1_2_4(self):
        """Tests user prompt: generate a open cv project from node 1 send it to review from node 2 then to node 4"""
        prompt = "generate a open cv project from node 1 send it to review from node 2 then to node 4 for further betterment"
        resp = self.client.post("/api/command", json={"command": prompt})
        self.assertEqual(resp.status_code, 200)
        task_id = resp.json().get("task_id")
        self.assertTrue(bool(task_id))

        # Check Node 1 heartbeat has picked up Stage 1 with 128K context window
        hb1 = self.client.post("/api/heartbeat", json={
            "node_id": "dgx-node-1", "status": "online", "active_model": "qwen2.5-coder:32b",
            "cpu_percent": 10.0, "ram_percent": 20.0, "gpu": {"utilization_pct": 0.0, "vram_used_mb": 0, "vram_total_mb": 131072, "temperature_c": 35}
        })
        self.assertEqual(hb1.status_code, 200)
        data1 = hb1.json()
        self.assertTrue(data1["has_task"])
        self.assertEqual(data1["task"]["model"], "qwen2.5-coder:32b")
        self.assertEqual(data1["task"]["num_ctx"], 131072)

        # Stage 1 completes on Node 1
        comp1 = self.client.post("/api/dgx/complete", json={
            "task_id": task_id, "node_id": "dgx-node-1", "exit_code": 0, "stdout": "import cv2\nprint('Stage 1 OpenCV code')",
            "generated_file": "opencv_project.py"
        })
        self.assertEqual(comp1.status_code, 200)

        # Node 2 heartbeat should now receive Stage 2 QA Review
        hb2 = self.client.post("/api/heartbeat", json={
            "node_id": "dgx-node-2", "status": "online", "active_model": "qwen2.5-coder:32b",
            "cpu_percent": 10.0, "ram_percent": 20.0, "gpu": {"utilization_pct": 0.0, "vram_used_mb": 0, "vram_total_mb": 131072, "temperature_c": 35}
        })
        self.assertEqual(hb2.status_code, 200)
        data2 = hb2.json()
        self.assertTrue(data2["has_task"])
        self.assertEqual(data2["task"]["model"], "qwen2.5-coder:32b")
        self.assertEqual(data2["task"]["num_ctx"], 65536)
        self.assertIn("prior_code", data2["task"])

        # Stage 2 completes on Node 2
        comp2 = self.client.post("/api/dgx/complete", json={
            "task_id": f"{task_id}_qa", "node_id": "dgx-node-2", "exit_code": 0, "stdout": "def test_opencv(): assert True",
            "generated_file": "test_suite.py"
        })
        self.assertEqual(comp2.status_code, 200)

        # Node 4 heartbeat should now receive Stage 3 Deep Reasoning & Betterment
        hb4 = self.client.post("/api/heartbeat", json={
            "node_id": "dgx-node-4", "status": "online", "active_model": "qwen2.5:32b",
            "cpu_percent": 10.0, "ram_percent": 20.0, "gpu": {"utilization_pct": 0.0, "vram_used_mb": 0, "vram_total_mb": 131072, "temperature_c": 35}
        })
        self.assertEqual(hb4.status_code, 200)
        data4 = hb4.json()
        self.assertTrue(data4["has_task"])
        self.assertEqual(data4["task"]["model"], "qwen2.5:32b")
        self.assertEqual(data4["task"]["num_ctx"], 131072)

        # Stage 3 completes on Node 4
        comp4 = self.client.post("/api/dgx/complete", json={
            "task_id": f"{task_id}_opt", "node_id": "dgx-node-4", "exit_code": 0, "stdout": "Optimized OpenCV code",
            "generated_file": "enhanced_solution.py"
        })
        self.assertEqual(comp4.status_code, 200)

if __name__ == "__main__":
    unittest.main()
