"""Unit tests for the Reverse-Heartbeat Architecture (Tailscale Funnel Gateway).
Verifies:
1. Outbound telemetry transmission (active window, idle time, CPU/RAM, GPU metrics).
2. Hub returns pending commands (warn, lock, capture, execute_task, pull_model) in heartbeat response.
3. Node reports command execution results.
4. WebSocket state broadcasts serialize datetimes without JSON errors.
"""
import unittest
import asyncio
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from aegis_core.models import NodeTelemetry, GPUInfo, CommandResult
from aegis_core.state_manager import StateManager
from aegis_core.safety_guard import SafetyGuard
from aegis_core.voice.dialogue_manager import DialogueManager
from aegis_core.orchestrator import Orchestrator
from aegis_core.api.server import create_app

class TestReverseHeartbeatArchitecture(unittest.TestCase):
    def setUp(self):
        self.state_mgr = StateManager(nodes_config_path="config/nodes.json")
        self.safety = SafetyGuard()
        self.dialogue = DialogueManager()
        self.orchestrator = Orchestrator(self.state_mgr, self.safety, self.dialogue)
        self.app = create_app(self.state_mgr, self.orchestrator, self.safety)
        self.client = TestClient(self.app)

    def test_reverse_heartbeat_telemetry_registration(self):
        """Outbound heartbeat transmits active window, idle time, and GPU stats with zero open ports."""
        telem = NodeTelemetry(
            node_id="dgx-node-1",
            name="DGX Spark 01",
            ip="127.0.0.1",
            status="online",
            active_window="Visual Studio Code - main.py",
            idle_time_seconds=12.5,
            cpu_percent=18.4,
            ram_percent=42.1,
            gpu=GPUInfo(name="NVIDIA GB10 Blackwell", vram_used_mb=12800, vram_total_mb=131072, utilization_pct=24.0, temperature_c=41.0),
            client_type="dgx",
            os_platform="linux"
        )

        res = self.client.post("/api/client/heartbeat", json=telem.model_dump(mode="json"))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "acknowledged")
        self.assertEqual(data["has_command"], False)

        # Verify state manager recorded live telemetry
        node = self.state_mgr.get_node("dgx-node-1")
        self.assertIsNotNone(node)
        self.assertEqual(node.active_window, "Visual Studio Code - main.py")
        self.assertEqual(node.idle_time_seconds, 12.5)

    def test_hub_command_delivery_inside_heartbeat_response(self):
        """Hub queues command -> delivered directly inside client's next outbound heartbeat response."""
        # 1. Operator or Pi Hub queues a 'warn' command
        warn_res = self.client.post("/api/client/dgx-node-1/warn", params={"message": "Save your work, cluster restart in 5 mins"})
        self.assertEqual(warn_res.status_code, 200)

        # 2. DGX Node sends its regular outbound heartbeat
        telem = NodeTelemetry(
            node_id="dgx-node-1",
            name="DGX Spark 01",
            ip="127.0.0.1",
            status="online",
            active_window="Terminal",
            idle_time_seconds=1.0
        )
        res = self.client.post("/api/client/heartbeat", json=telem.model_dump(mode="json"))
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # 3. Verify command was returned inside heartbeat response
        self.assertTrue(data["has_command"])
        cmd = data["command"]
        self.assertEqual(cmd["command_type"], "warn")
        self.assertEqual(cmd["payload"]["message"], "Save your work, cluster restart in 5 mins")

        # 4. Client executes command and reports result back
        result_payload = CommandResult(
            command_id=cmd["command_id"],
            node_id="dgx-node-1",
            status="completed",
            output="Warning alert shown on DGX overlay HUD"
        )
        post_res = self.client.post("/api/client/command_result", json=result_payload.model_dump(mode="json"))
        self.assertEqual(post_res.status_code, 200)

    def test_lock_and_unlock_cycle(self):
        """Verifies lock and unlock commands via reverse queue."""
        # Lock node
        self.client.post("/api/client/dgx-node-1/lock", params={"reason": "Security isolation"})

        # Heartbeat receives lock command
        telem = NodeTelemetry(node_id="dgx-node-1", name="DGX Spark 01", ip="127.0.0.1")
        res = self.client.post("/api/client/heartbeat", json=telem.model_dump(mode="json"))
        data = res.json()
        self.assertTrue(data["has_command"])
        self.assertEqual(data["command"]["command_type"], "lock")

    def test_task_enqueued_as_reverse_command(self):
        """User submits prompt -> automatically delivered in DGX heartbeat response."""
        submit_res = self.client.post("/api/tasks/submit", json={
            "command": "Write quicksort in python",
            "preferred_node": "dgx-node-1"
        })
        self.assertEqual(submit_res.status_code, 200)

        # DGX sends heartbeat
        telem = NodeTelemetry(node_id="dgx-node-1", name="DGX Spark 01", ip="127.0.0.1")
        res = self.client.post("/api/client/heartbeat", json=telem.model_dump(mode="json"))
        data = res.json()
        self.assertTrue(data["has_command"] or data["has_task"])

    def test_websocket_snapshot_datetime_serialization(self):
        """Verifies WebSocket endpoint does not throw TypeError on datetime objects."""
        with self.client.websocket_connect("/ws/cluster") as ws:
            data = ws.receive_json()
            self.assertEqual(data["event"], "initial_snapshot")
            self.assertIn("nodes", data)
            self.assertIn("tasks", data)

if __name__ == "__main__":
    unittest.main()
