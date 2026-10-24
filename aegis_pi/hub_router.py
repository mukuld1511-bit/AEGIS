"""AEGIS Raspberry Pi Central Hub Router.
Orchestrates the 4 flagship DGX Spark nodes via Hub-and-Spoke topology.
Enforces strict node isolation, manages multi-agent handoffs, and resolves node configs dynamically.
"""
import os
import json
import asyncio
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from aegis_core.models import TaskRecord, TaskStep
from aegis_core.storage_manager import AEGISStorageSystem
from aegis_core.safety_guard import SafetyGuard
from aegis_core.voice.dialogue_manager import DialogueManager

class PiHubRouter:
    def __init__(self, nodes_config_path: str = "config/nodes.json"):
        self.storage = AEGISStorageSystem(remote_name="gdrive", base_folder="AEGIS_Cluster_Artifacts")
        self.safety = SafetyGuard()
        self.dialogue = DialogueManager()
        self.nodes_config_path = nodes_config_path
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.nodes_metadata: Dict[str, Dict[str, Any]] = self._load_nodes_config()

    def _load_nodes_config(self) -> Dict[str, Dict[str, Any]]:
        """Dynamically loads node IPs, ports, and models from config/nodes.json."""
        resolved: Dict[str, Dict[str, Any]] = {}
        path = self.nodes_config_path
        if not os.path.exists(path):
            alt_path = os.path.join(os.path.dirname(__file__), "..", "config", "nodes.json")
            if os.path.exists(alt_path):
                path = alt_path

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for n in data.get("nodes", []):
                        resolved[n["id"]] = n
            except Exception as e:
                print(f"[!] Warning: Failed to parse nodes.json ({e})")

        # Fallback defaults for flagship cluster
        if not resolved:
            resolved = {
                "dgx-node-1": {"id": "dgx-node-1", "name": "DGX Spark 01 - Lead Coder", "model_tag": "qwen2.5-coder:32b", "tailscale_ip": "100.106.207.101", "port": 8801},
                "dgx-node-2": {"id": "dgx-node-2", "name": "DGX Spark 02 - Reviewer & QA", "model_tag": "qwen2.5-coder:32b", "tailscale_ip": "100.106.207.102", "port": 8802},
                "dgx-node-3": {"id": "dgx-node-3", "name": "DGX Spark 03 - Vision & Arch", "model_tag": "llama3.2-vision:90b", "tailscale_ip": "100.106.207.103", "port": 8803},
                "dgx-node-4": {"id": "dgx-node-4", "name": "DGX Spark 04 - Deep Reasoner", "model_tag": "mixtral:8x22b", "tailscale_ip": "100.106.207.104", "port": 8804},
            }
        return resolved

    def get_node(self, node_id: str) -> Dict[str, Any]:
        return self.nodes_metadata.get(node_id, {
            "id": node_id,
            "tailscale_ip": "127.0.0.1",
            "port": 8801,
            "model_tag": "qwen2.5-coder:32b"
        })

    def parse_user_request(self, raw_prompt: str) -> Dict[str, Any]:
        """Classifies voice/text request in Hindi, Hinglish, or English."""
        return self.dialogue.parse(raw_prompt)

    async def dispatch_task(self, prompt: str, target_node: str = "dgx-node-1") -> Dict[str, Any]:
        """Dispatches a task to a designated DGX node with storage manifests and context windows."""
        node_cfg = self.get_node(target_node)
        manifest = self.storage.create_task_storage_manifest()
        task_id = manifest["task_id"]

        expected_file = "solution.py"
        upload_cmd = self.storage.generate_worker_upload_command(manifest, f"./workspace/{expected_file}")

        payload = {
            "task_id": task_id,
            "prompt": prompt,
            "model": node_cfg.get("model_tag", "qwen2.5-coder:32b"),
            "num_ctx": 65536,
            "expected_file": expected_file,
            "dictated_upload_cmd": upload_cmd,
            "storage_vault_url": f"http://100.88.197.6:9080/api/storage/{target_node}/upload/{task_id}",
            "callback_url": "http://100.106.207.27:9000/api/dgx/complete"
        }

        self.active_tasks[task_id] = {
            "task_id": task_id,
            "prompt": prompt,
            "manifest": manifest,
            "primary_node": target_node,
            "current_stage": "stage_1_code_generation",
            "status": "dispatched",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Attempt direct dispatch over Tailscale; if node operates in reverse mode, task is queued
        target_ip = node_cfg.get("tailscale_ip", "100.106.207.101")
        port = node_cfg.get("port", 8801)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(f"http://{target_ip}:{port}/api/execute", json=payload)
                if res.status_code == 200:
                    return {"status": "dispatched_direct", "task_id": task_id, "manifest": manifest}
        except Exception:
            pass

        return {"status": "enqueued_in_hub", "task_id": task_id, "manifest": manifest, "payload": payload}

    async def handle_node_completion_and_handoff(self, task_id: str, primary_result: Dict[str, Any], next_stage_node: Optional[str] = None) -> Dict[str, Any]:
        """Orchestrates multi-stage autonomous pipeline across Nodes 1, 2, 3, and 4."""
        if task_id not in self.active_tasks:
            return {"error": "Unknown task ID"}

        task_info = self.active_tasks[task_id]
        manifest = task_info["manifest"]
        from_node = primary_result.get("node_id", task_info.get("primary_node", "dgx-node-1"))
        filename = primary_result.get("generated_file", "solution.py")

        # Determine next pipeline stage
        pipeline_sequence = {
            "dgx-node-1": ("dgx-node-2", "qa_review", "Review this code, verify logical edge cases, write test_suite.py, and produce QA_AUDIT_REPORT.md"),
            "dgx-node-2": ("dgx-node-3", "architecture_vision", "Analyze the reviewed solution, generate Mermaid.js system architecture diagrams, and create UI specifications"),
            "dgx-node-3": ("dgx-node-4", "deep_reasoning", "Audit security attack surface, perform computational complexity analysis, and summarize into RFC design document"),
            "dgx-node-4": (None, "pipeline_complete", "All 4 DGX Spark specialized nodes have successfully verified and published artifacts")
        }

        to_node, action, handoff_prompt = pipeline_sequence.get(from_node, (None, "complete", "Pipeline concluded"))
        if next_stage_node:
            to_node = next_stage_node

        if not to_node:
            task_info["status"] = "pipeline_completed"
            return {
                "status": "pipeline_completed",
                "task_id": task_id,
                "summary": f"Completed 4-stage multi-agent pipeline from {from_node}."
            }

        next_cfg = self.get_node(to_node)
        dl_cmd = self.storage.generate_handoff_download_command(manifest, filename, stage="outputs", local_dest="./review_workspace")

        handoff_payload = {
            "task_id": f"{task_id}_{to_node[-1]}",
            "parent_task_id": task_id,
            "action": action,
            "dictated_download_cmd": dl_cmd,
            "target_file": f"./review_workspace/{filename}",
            "prompt": f"{handoff_prompt}.\n\nOriginal Task: {task_info['prompt']}\nFile: {filename}",
            "model": next_cfg.get("model_tag", "qwen2.5-coder:32b"),
            "num_ctx": 65536,
            "storage_vault_url": f"http://100.88.197.6:9080/api/storage/{to_node}/upload/{task_id}_{to_node[-1]}"
        }

        # Forward to next specialized DGX node
        target_ip = next_cfg.get("tailscale_ip", "127.0.0.1")
        port = next_cfg.get("port", 8802)
        dispatched = False
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(f"http://{target_ip}:{port}/api/execute", json=handoff_payload)
                if res.status_code == 200:
                    dispatched = True
        except Exception:
            pass

        task_info["current_stage"] = f"in_{action}_on_{to_node}"
        task_info["status"] = "dispatched" if dispatched else "enqueued"

        return {
            "status": "handoff_orchestrated",
            "task_id": task_id,
            "from_node": from_node,
            "to_node": to_node,
            "action": action,
            "model": next_cfg.get("model_tag"),
            "dictated_download_cmd": dl_cmd,
            "dispatched_direct": dispatched
        }
