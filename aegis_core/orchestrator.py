"""AEGIS Core Orchestrator.
Intelligent routing, multi-node task planning, evidence-gated safety, and cluster coordination.
"""
import asyncio
from typing import Dict, Any, Optional, List
from aegis_core.state_manager import StateManager
from aegis_core.safety_guard import SafetyGuard
from aegis_core.voice.dialogue_manager import DialogueManager
from aegis_core.models import TaskRecord, TaskStep

class Orchestrator:
    def __init__(self, state_manager: StateManager, safety_guard: SafetyGuard, dialogue_mgr: DialogueManager):
        self.state = state_manager
        self.safety = safety_guard
        self.dialogue = dialogue_mgr

    def select_best_node(self, required_capability: str, preferred_node: Optional[str] = None) -> str:
        """Selects optimal DGX node based on capability, health, and current load."""
        if preferred_node and preferred_node in self.state.nodes:
            node = self.state.nodes[preferred_node]
            if node.status in ["online", "busy"]:
                return preferred_node

        # Capability matching
        candidates = []
        for nid, node in self.state.nodes.items():
            if node.status == "online":
                if required_capability in node.capabilities or not required_capability:
                    candidates.append(node)

        if not candidates:
            # Fallback to any online node
            online = self.state.get_online_nodes()
            return online[0].node_id if online else "dgx-node-1"

        # Sort by lowest GPU utilization and VRAM usage
        candidates.sort(key=lambda n: (n.gpu.utilization_pct, n.gpu.vram_used_mb))
        return candidates[0].node_id

    async def handle_user_command(self, raw_command: str, preferred_node: Optional[str] = None) -> Dict[str, Any]:
        """End-to-end processing pipeline for natural voice or text command."""
        parsed = self.dialogue.parse(raw_command)
        intent = parsed["intent"]
        lang = parsed["language"]
        target_node = preferred_node or parsed["target_node"]
        cleaned_prompt = parsed["cleaned_prompt"]

        # 1. Informational / Query Intents
        if intent == "CLUSTER_STATUS":
            online_nodes = len([n for n in self.state.nodes.values() if n.status in ["online", "busy"]])
            speech = self.dialogue.generate_response_text(intent, {"online_nodes": online_nodes, "total_nodes": len(self.state.nodes)}, lang)
            return {
                "status": "success",
                "intent": intent,
                "spoken_response": speech,
                "cluster_summary": {nid: n.status for nid, n in self.state.nodes.items()}
            }

        # 2. Safety / Shutdown Intents
        elif intent == "SHUTDOWN_NODE":
            node_id = target_node or "dgx-node-5"
            cmd = f"shutdown -h now"
            eval_res = self.safety.evaluate_command(cmd)
            warning_speech = self.safety.format_warning_speech(eval_res, lang)
            return {
                "status": "awaiting_approval",
                "intent": intent,
                "target_node": node_id,
                "safety_evaluation": eval_res.model_dump(),
                "spoken_response": warning_speech
            }

        # 3. Action Intents (Code, Data Analysis, Reasoning)
        required_cap = "code_generation"
        if "data" in cleaned_prompt or "csv" in cleaned_prompt:
            required_cap = "data_analysis"
        elif "reason" in cleaned_prompt or "plan" in cleaned_prompt:
            required_cap = "complex_reasoning"

        assigned_node_id = self.select_best_node(required_cap, preferred_node=target_node)
        reviewer_node_id = "dgx-node-2" if assigned_node_id != "dgx-node-2" else "dgx-node-8"

        # Create task record
        title = raw_command[:45] + "..." if len(raw_command) > 45 else raw_command
        task = self.state.create_task(
            title=title,
            prompt=raw_command,
            assigned_node_id=assigned_node_id,
            reviewer_node_id=reviewer_node_id,
            lang=lang
        )

        # Create initial execution step
        node_obj = self.state.get_node(assigned_node_id)
        node_name = node_obj.name if node_obj else assigned_node_id
        step1 = TaskStep(
            node_id=assigned_node_id,
            description=f"Initial execution step on {node_name}",
            command=f"python -m aegis_worker --task {task.task_id} --prompt '{cleaned_prompt}'",
            status="running"
        )
        self.state.add_task_step(task.task_id, step1)

        speech = self.dialogue.generate_response_text(
            "CODE_TASK" if required_cap == "code_generation" else intent,
            {"node_name": node_name, "reviewer_node": reviewer_node_id},
            lang
        )

        return {
            "status": "task_scheduled",
            "task_id": task.task_id,
            "assigned_node": assigned_node_id,
            "reviewer_node": reviewer_node_id,
            "spoken_response": speech,
            "task": task.model_dump()
        }

    async def execute_task_simulation_step(self, task_id: str, step_id: str, log_chunk: str, is_done: bool = False):
        """Simulates or streams live execution chunk from a node agent."""
        self.state.update_task_step(task_id, step_id, status="completed" if is_done else "running", stdout=log_chunk)
        if is_done:
            self.state.complete_task(task_id, summary=f"Task {task_id} completed successfully with verified artifacts.")
