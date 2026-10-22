"""AEGIS State Manager.
Maintains in-memory and persisted cluster state: node telemetry, task queues, and event dispatch.
"""
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from aegis_core.models import NodeTelemetry, TaskRecord, TaskStep, GPUInfo

class StateManager:
    def __init__(self, nodes_config_path: str = "config/nodes.json"):
        self.nodes_config_path = nodes_config_path
        self.nodes: Dict[str, NodeTelemetry] = {}
        self.tasks: Dict[str, TaskRecord] = {}
        self.event_subscribers: List[Callable] = []
        self._load_initial_nodes()

    def _load_initial_nodes(self):
        """Loads static inventory of nodes from configuration file."""
        try:
            with open(self.nodes_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("nodes", []):
                    node = NodeTelemetry(
                        node_id=item["id"],
                        name=item["name"],
                        ip=item["ip"],
                        status="online",
                        active_model=item.get("default_model", ""),
                        capabilities=item.get("capabilities", []),
                        gpu=GPUInfo(
                            name=item.get("gpu", "NVIDIA DGX Spark"),
                            vram_total_mb=item.get("vram_gb", 80) * 1024,
                            vram_used_mb=4096.0, # base idle footprint
                            utilization_pct=2.0,
                            temperature_c=38.0
                        )
                    )
                    self.nodes[node.node_id] = node
        except Exception as e:
            print(f"[StateManager] Warning: Could not load nodes config: {e}")

    def register_heartbeat(self, telemetry: NodeTelemetry):
        """Updates live telemetry received from a DGX or Lab PC node."""
        telemetry.last_heartbeat = datetime.now(timezone.utc)
        self.nodes[telemetry.node_id] = telemetry
        self._broadcast("node_telemetry_updated", telemetry.model_dump(mode="json"))

    def update_node_status(self, node_id: str, status: str, current_task_id: Optional[str] = None):
        if node_id in self.nodes:
            self.nodes[node_id].status = status
            self.nodes[node_id].current_task_id = current_task_id
            self._broadcast("node_status_changed", {"node_id": node_id, "status": status, "task_id": current_task_id})

    def get_online_nodes(self) -> List[NodeTelemetry]:
        return [n for n in self.nodes.values() if n.status in ["online", "busy"]]

    def get_node(self, node_id: str) -> Optional[NodeTelemetry]:
        return self.nodes.get(node_id)

    def create_task(self, title: str, prompt: str, assigned_node_id: str, reviewer_node_id: Optional[str] = None, lang: str = "hi-en") -> TaskRecord:
        task = TaskRecord(
            title=title,
            prompt=prompt,
            assigned_node_id=assigned_node_id,
            reviewer_node_id=reviewer_node_id,
            language=lang,
            status="queued"
        )
        self.tasks[task.task_id] = task
        self.update_node_status(assigned_node_id, "busy", task.task_id)
        self._broadcast("task_created", task.model_dump(mode="json"))
        return task

    def add_task_step(self, task_id: str, step: TaskStep):
        if task_id in self.tasks:
            self.tasks[task_id].steps.append(step)
            self.tasks[task_id].updated_at = datetime.now(timezone.utc)
            self._broadcast("task_step_added", {"task_id": task_id, "step": step.model_dump(mode="json")})

    def update_task_step(self, task_id: str, step_id: str, status: str, stdout: str = "", stderr: str = ""):
        if task_id in self.tasks:
            for s in self.tasks[task_id].steps:
                if s.step_id == step_id:
                    s.status = status
                    if stdout:
                        s.stdout += stdout
                    if stderr:
                        s.stderr += stderr
                    if status in ["completed", "failed"]:
                        s.completed_at = datetime.now(timezone.utc)
                    self._broadcast("task_step_updated", {"task_id": task_id, "step_id": step_id, "status": status, "stdout": s.stdout})
                    break

    def complete_task(self, task_id: str, summary: str, status: str = "completed"):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = status
            task.result_summary = summary
            task.updated_at = datetime.now(timezone.utc)
            self.update_node_status(task.assigned_node_id, "online", None)
            self._broadcast("task_completed", task.model_dump(mode="json"))

    def subscribe(self, callback: Callable):
        self.event_subscribers.append(callback)

    def _broadcast(self, event_type: str, data: Any):
        payload = {"event": event_type, "timestamp": datetime.now(timezone.utc).isoformat(), "data": data}
        for sub in self.event_subscribers:
            try:
                if asyncio.iscoroutinefunction(sub):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(sub(payload))
                    except RuntimeError:
                        pass
                else:
                    sub(payload)
            except Exception:
                pass

