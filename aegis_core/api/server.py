"""AEGIS Central Control API Server (Reverse-Heartbeat Architecture).
Raspberry Pi Gateway exposed via Tailscale Funnel (https://raspberrypi.tailc8c1f6.ts.net).
DGX nodes poll outbound via HTTPS heartbeats; pending tasks are delivered in heartbeat responses.
Zero inbound ports required on student / compute nodes.
"""
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from collections import defaultdict
import asyncio
import json
import time

from aegis_core.models import NodeTelemetry, TaskRecord, HeartbeatCommand, CommandResult
from aegis_core.state_manager import StateManager
from aegis_core.safety_guard import SafetyGuard
from aegis_core.voice.dialogue_manager import DialogueManager
from aegis_core.orchestrator import Orchestrator

DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "aegis_server", "dashboard"))

def create_app(state_mgr: StateManager, orchestrator: Orchestrator, safety: SafetyGuard) -> FastAPI:
    app = FastAPI(title="AEGIS Central Control Plane (Tailscale Funnel)", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach Storage Vault routes directly so port 9000 & Tailscale Funnel serve them seamlessly
    try:
        from aegis_server.storage_service import app as storage_app
        for r in storage_app.routes:
            if hasattr(r, 'path') and r.path.startswith('/api/storage'):
                app.routes.append(r)
    except Exception as e:
        print("[AEGIS CORE] Note: storage_service routes not attached:", e)

    active_ws_connections: List[WebSocket] = []
    # Reverse-Heartbeat task and command queues for all nodes
    node_task_queues: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    client_command_queues: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    latest_screenshots: Dict[str, str] = {}

    # Broadcast state updates to WebSocket clients
    async def ws_broadcaster(event_payload: Dict[str, Any]):
        dead_conns = []
        for ws in active_ws_connections:
            try:
                await ws.send_json(event_payload)
            except Exception:
                dead_conns.append(ws)
        for dc in dead_conns:
            if dc in active_ws_connections:
                active_ws_connections.remove(dc)

    state_mgr.subscribe(ws_broadcaster)

    class CommandInput(BaseModel):
        command: str
        preferred_node: Optional[str] = None
        pc_id: Optional[str] = None
        session_id: Optional[str] = "default_session"

    class ClientCommandPush(BaseModel):
        node_id: str
        command_type: str # warn, lock, unlock, shutdown, capture, execute_task, pull_model, run_command
        payload: Dict[str, Any] = {}

    class ApprovalInput(BaseModel):
        approved: bool
        override_reason: Optional[str] = None

    class DGXCompletePayload(BaseModel):
        task_id: str
        node_id: str
        exit_code: int = 0
        stdout: str = ""
        stderr: str = ""
        generated_file: Optional[str] = None
        vault_status: Optional[str] = None
        drive_status: Optional[str] = None

    DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "aegis_server", "dashboard"))

    @app.get("/")
    def root():
        index_path = os.path.join(DASHBOARD_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {
            "system": "AEGIS Central Gateway",
            "gateway": "https://raspberrypi.tailc8c1f6.ts.net",
            "status": "online"
        }

    @app.get("/api/gateway")
    def get_gateway_info():
        return {
            "system": "AEGIS Central Gateway",
            "gateway": "https://raspberrypi.tailc8c1f6.ts.net",
            "architecture": "Reverse-Heartbeat (Outbound Polling)",
            "telemetry_interval": "6 seconds",
            "open_inbound_ports_required": 0,
            "status": "online"
        }

    @app.get("/api/status")
    def get_cluster_status():
        online_count = len([n for n in state_mgr.nodes.values() if n.status in ["online", "busy", "locked"]])
        queued_tasks = sum(len(q) for q in node_task_queues.values())
        queued_cmds = sum(len(q) for q in client_command_queues.values())
        return {
            "status": "active",
            "total_nodes": len(state_mgr.nodes),
            "online_nodes": online_count,
            "active_tasks": len([t for t in state_mgr.tasks.values() if t.status in ["queued", "running", "awaiting_approval"]]),
            "pending_reverse_tasks": queued_tasks,
            "pending_reverse_commands": queued_cmds
        }

    @app.get("/api/nodes", response_model=List[NodeTelemetry])
    def get_nodes():
        return list(state_mgr.nodes.values())

    @app.get("/api/nodes/{node_id}", response_model=NodeTelemetry)
    def get_node(node_id: str):
        node = state_mgr.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        return node

    @app.post("/api/heartbeat")
    @app.post("/api/dgx/heartbeat")
    @app.post("/api/client/heartbeat")
    @app.post("/api/pc/heartbeat")
    def reverse_heartbeat_poll(telemetry: NodeTelemetry):
        """
        Reverse-Heartbeat Core Endpoint (Piet Architecture):
        Lab PCs and DGX nodes poll outbound via HTTPS every 6s (Zero inbound open ports).
        Bypasses strict college firewalls and NAT completely.
        Returns pending commands (warn, lock, shutdown, capture, execute_task, pull_model, run_command)
        directly inside the heartbeat HTTP response.
        """
        if telemetry.screenshot_b64:
            latest_screenshots[telemetry.node_id] = telemetry.screenshot_b64

        state_mgr.register_heartbeat(telemetry)

        # Check for administrative supervisor command (warn, lock, shutdown, capture)
        cmd_item = None
        cmd_queue = client_command_queues[telemetry.node_id]
        if cmd_queue:
            cmd_item = cmd_queue.pop(0)

        # Check for AI compute task
        task_item = None
        task_queue = node_task_queues[telemetry.node_id]
        if task_queue:
            task_item = task_queue.pop(0)

        # If a task is present, wrap it into command format if no explicit admin command exists
        if not cmd_item and task_item:
            cmd_item = {
                "command_id": task_item.get("task_id", f"cmd-{int(time.time())}"),
                "command_type": "execute_task",
                "payload": task_item
            }

        return {
            "status": "acknowledged",
            "node_id": telemetry.node_id,
            "has_command": bool(cmd_item),
            "command": cmd_item,
            "has_task": bool(task_item),
            "task": task_item
        }

    @app.post("/api/client/command")
    def push_client_command(cmd_req: ClientCommandPush):
        """Dispatches a command (warn, lock, unlock, shutdown, capture, run_command, pull_model)
        into the client node's outbound reverse queue.
        """
        cmd_id = f"cmd-{int(time.time())}"
        cmd_dict = {
            "command_id": cmd_id,
            "command_type": cmd_req.command_type,
            "payload": cmd_req.payload
        }
        client_command_queues[cmd_req.node_id].append(cmd_dict)
        state_mgr._broadcast("client_command_queued", {"node_id": cmd_req.node_id, "command": cmd_dict})
        return {
            "status": "queued",
            "command_id": cmd_id,
            "node_id": cmd_req.node_id,
            "command_type": cmd_req.command_type,
            "message": "Will be delivered on client's next 6s outbound heartbeat"
        }

    @app.post("/api/client/command_result")
    def receive_command_result(result: CommandResult):
        """Called by client agent when a command (warn, capture, run_command) finishes."""
        if result.screenshot_b64:
            latest_screenshots[result.node_id] = result.screenshot_b64

        state_mgr._broadcast("client_command_finished", result.model_dump(mode="json"))
        return {"status": "recorded", "command_id": result.command_id}

    @app.post("/api/client/{node_id}/warn")
    def warn_node(node_id: str, message: str = "Administrator warning message"):
        return push_client_command(ClientCommandPush(
            node_id=node_id,
            command_type="warn",
            payload={"message": message}
        ))

    @app.post("/api/client/{node_id}/lock")
    def lock_node(node_id: str, reason: str = "Locked by Lab Administrator"):
        return push_client_command(ClientCommandPush(
            node_id=node_id,
            command_type="lock",
            payload={"reason": reason}
        ))

    @app.post("/api/client/{node_id}/unlock")
    def unlock_node(node_id: str):
        return push_client_command(ClientCommandPush(
            node_id=node_id,
            command_type="unlock",
            payload={}
        ))

    @app.post("/api/client/{node_id}/capture")
    def capture_screenshot_node(node_id: str):
        return push_client_command(ClientCommandPush(
            node_id=node_id,
            command_type="capture",
            payload={"quality": "high"}
        ))

    @app.post("/api/client/{node_id}/shutdown")
    def shutdown_node(node_id: str, reason: str = "Authorized remote shutdown"):
        return push_client_command(ClientCommandPush(
            node_id=node_id,
            command_type="shutdown",
            payload={"reason": reason}
        ))

    @app.get("/api/client/{node_id}/screenshot")
    def get_latest_screenshot(node_id: str):
        shot = latest_screenshots.get(node_id)
        if not shot:
            # check telemetry
            node = state_mgr.get_node(node_id)
            if node and node.screenshot_b64:
                shot = node.screenshot_b64
        if not shot:
            raise HTTPException(status_code=404, detail="No screenshot available for node")
        return {"node_id": node_id, "screenshot_b64": shot}

    @app.get("/api/client/summary")
    def get_lab_clients_summary():
        """Summary of active windows, idle times, and telemetry for all client nodes."""
        summary = []
        for n in state_mgr.nodes.values():
            summary.append({
                "node_id": n.node_id,
                "name": n.name,
                "status": n.status,
                "active_window": n.active_window,
                "idle_time_seconds": n.idle_time_seconds,
                "cpu_percent": n.cpu_percent,
                "ram_percent": n.ram_percent,
                "gpu_utilization": n.gpu.utilization_pct,
                "vram_used_mb": n.gpu.vram_used_mb,
                "vram_total_mb": n.gpu.vram_total_mb,
                "has_screenshot": n.node_id in latest_screenshots or bool(n.screenshot_b64),
                "last_heartbeat": n.last_heartbeat.isoformat()
            })
        return summary

    @app.post("/api/dgx/complete")
    async def dgx_task_completed(payload: DGXCompletePayload):
        """Called by DGX agent when a task finishes execution."""
        state_mgr.complete_task(payload.task_id, summary=payload.stdout[:200])
        state_mgr._broadcast("dgx_task_finished", payload.model_dump(mode="json"))

        # Determine if this task is part of the 4-node autonomous pipeline:
        # dgx-node-1 (Coder) -> dgx-node-2 (QA & Review) -> dgx-node-3 (Vision & Arch) -> dgx-node-4 (Deep Reasoner & Security)
        task_id = payload.task_id
        storage_base = "http://100.88.197.6:9080/api/storage"

        next_stage = None
        orig_task = task_id
        if task_id.endswith("_sec") or task_id.endswith("_opt"):
            # Final pipeline stage completed on dgx-node-4
            orig_task = task_id[:-4]
            state_mgr._broadcast("pipeline_completed", {
                "original_task_id": orig_task,
                "final_node": payload.node_id,
                "summary": "Full multi-node cluster synthesis, QA review & deep betterment pipeline completed successfully."
            })
        elif task_id.endswith("_arch"):
            # Stage 3 completed on dgx-node-3 -> handoff to dgx-node-4
            orig_task = task_id[:-5]
            next_stage = {
                "target_node": "dgx-node-4",
                "task_id": f"{orig_task}_opt",
                "model": "mixtral:8x22b",
                "num_ctx": 65536,
                "prompt": (
                    f"You are the Principal Sentinel & Deep Reasoner on DGX Node 4.\n"
                    f"Perform deep architectural betterment and vulnerability audit on task '{orig_task}'.\n"
                    f"Stage 1 code, Stage 2 QA report, and Stage 3 Architectural assessment are present in your workspace.\n\n"
                    f"Provide formal correctness verification and output the certified hardened implementation.\n"
                    f"Prefix final production file with '# filename: enhanced_solution.py' on line 1."
                ),
                "stage_name": "Stage 4: Deep Reasoning & System Betterment"
            }
        elif task_id.endswith("_qa") or task_id.endswith("_rev"):
            # Stage 2 completed on dgx-node-2 -> handoff directly to dgx-node-4 (Deep Reasoner & Betterment)
            orig_task = task_id[:-3] if task_id.endswith("_qa") else task_id[:-4]
            next_stage = {
                "target_node": "dgx-node-4",
                "task_id": f"{orig_task}_opt",
                "model": "mixtral:8x22b",
                "num_ctx": 65536,
                "prompt": (
                    f"You are DGX Spark 04 - Deep Reasoner & System Optimizer.\n"
                    f"Perform deep betterment, enhancement, and optimization on task '{orig_task}'.\n"
                    f"Original Stage 1 code and Stage 2 QA test suite:\n\n"
                    f"{payload.stdout[:2500]}\n\n"
                    f"Enhance and optimize this implementation with advanced features, real-time streaming, and robust error handling.\n"
                    f"Save your enhanced solution with '# filename: enhanced_opencv_studio.py' on line 1."
                ),
                "stage_name": "Stage 3: Deep Reasoning & System Betterment"
            }
        elif payload.node_id == "dgx-node-1":
            # Stage 1 completed on dgx-node-1 -> handoff to dgx-node-2
            next_stage = {
                "target_node": "dgx-node-2",
                "task_id": f"{orig_task}_qa",
                "model": "qwen2.5-coder:32b",
                "num_ctx": 65536,
                "prompt": (
                    f"You are the Lead QA & Code Reviewer on DGX Node 2.\n"
                    f"Review the generated code for task '{orig_task}' executed by Node 1:\n\n"
                    f"{payload.stdout[:2000]}\n\n"
                    f"Write comprehensive pytest unit tests and edge-case validations.\n"
                    f"Save your tests with '# filename: test_suite.py' on the first line."
                ),
                "stage_name": "Stage 2: QA Review & Test Automation"
            }

        if next_stage:
            t_node = next_stage["target_node"]
            handoff_task = {
                "task_id": next_stage["task_id"],
                "prompt": next_stage["prompt"],
                "command": None,
                "model": next_stage["model"],
                "num_ctx": next_stage.get("num_ctx", 65536),
                "target_file": payload.generated_file,
                "dictated_upload_cmd": None,
                "is_pipeline_handoff": True,
                "parent_task_id": payload.task_id,
                "storage_vault_url": f"{storage_base}/{t_node}/upload/{next_stage['task_id']}"
            }
            node_task_queues[t_node].append(handoff_task)
            state_mgr.update_node_status(t_node, "busy", next_stage["task_id"])
            state_mgr._broadcast("pipeline_step_progress", {
                "original_task_id": orig_task,
                "next_node": t_node,
                "stage": next_stage["stage_name"],
                "task": handoff_task
            })

        return {"status": "recorded", "task_id": payload.task_id}

    @app.post("/api/tasks/submit")
    @app.post("/api/command")
    async def submit_command(payload: CommandInput):
        """User or voice submits command -> enqueued into the assigned DGX node's reverse queue."""
        pref_node = payload.preferred_node or payload.pc_id
        res = await orchestrator.handle_user_command(payload.command, preferred_node=pref_node)
        if res.get("status") in ["task_scheduled", "completed"]:
            assigned_node = res.get("assigned_node", pref_node or "dgx-node-1")
            task_id = res.get("task_id")

            # Enqueue for reverse heartbeat pick-up
            task_payload = {
                "task_id": task_id,
                "prompt": payload.command,
                "command": None, # Will run local Ollama LLM on DGX
                "model": "qwen2.5-coder:32b",
                "num_ctx": 65536,
                "dictated_upload_cmd": f"rclone copyto ./workspace/{task_id}_output.py gdrive:/AEGIS_Cluster_Artifacts/{task_id}/ || true",
                "storage_vault_url": f"http://100.88.197.6:9080/api/storage/{assigned_node}/upload/{task_id}"
            }
            node_task_queues[assigned_node].append(task_payload)
            state_mgr._broadcast("task_enqueued_in_reverse_hub", {"node": assigned_node, "task": task_payload})

        return res

    @app.get("/api/tasks", response_model=List[TaskRecord])
    def list_tasks():
        return list(state_mgr.tasks.values())

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        if task_id not in state_mgr.tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        return state_mgr.tasks[task_id]

    @app.post("/api/tasks/{task_id}/approve")
    def approve_task_step(task_id: str, payload: ApprovalInput):
        if task_id not in state_mgr.tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        task = state_mgr.tasks[task_id]
        if payload.approved:
            task.status = "running"
            state_mgr._broadcast("task_approved", {"task_id": task_id, "approved": True})
            return {"status": "approved", "task_id": task_id}
        else:
            task.status = "failed"
            task.result_summary = "Operation rejected by user / safety gate."
            state_mgr._broadcast("task_rejected", {"task_id": task_id, "reason": payload.override_reason})
            return {"status": "rejected", "task_id": task_id}

    @app.websocket("/ws/cluster")
    async def websocket_cluster_endpoint(websocket: WebSocket):
        await websocket.accept()
        active_ws_connections.append(websocket)
        try:
            snapshot = {
                "event": "initial_snapshot",
                "nodes": [n.model_dump(mode="json") for n in state_mgr.nodes.values()],
                "tasks": [t.model_dump(mode="json") for t in state_mgr.tasks.values()]
            }
            await websocket.send_json(snapshot)
            while True:
                data = await websocket.receive_text()
                try:
                    parsed = json.loads(data)
                    if parsed.get("action") == "voice_command":
                        cmd_text = parsed.get("command", "")
                        result = await orchestrator.handle_user_command(cmd_text)
                        await websocket.send_json({"event": "command_result", "data": result})
                except Exception:
                    pass
        except WebSocketDisconnect:
            if websocket in active_ws_connections:
                active_ws_connections.remove(websocket)



    if os.path.exists(DASHBOARD_DIR):
        app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard_static")

    return app

