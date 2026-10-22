"""AEGIS Node Agent Service.
Runs on each NVIDIA DGX Spark node. Manages local execution, GPU telemetry, persistent terminals, and HUD.
Exposes /api/execute for receiving direct curl/URL commands from Raspberry Pi over Tailscale.
"""
import asyncio
import json
import httpx
import argparse
import sys
import os
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from aegis_core.models import NodeTelemetry, GPUInfo
from aegis_node.gpu_telemetry import GPUTelemetryReporter
from aegis_node.terminal_session import TerminalSession
from aegis_node.llm_runner import LLMRunner
from aegis_node.overlay.overlay_hud import OverlayHUD

class ExecutePayload(BaseModel):
    task_id: Optional[str] = None
    prompt: str
    command: Optional[str] = None
    dictated_upload_cmd: Optional[str] = None
    callback_url: Optional[str] = None

class DGXNodeAgent:
    def __init__(self, node_id: str, port: int = 8801, coordinator_url: str = "http://100.106.207.27:9000", artifact_server_url: str = "http://100.88.197.6:9080", show_hud: bool = False):
        self.node_id = node_id
        self.port = port
        self.coordinator_url = coordinator_url.rstrip("/")
        self.artifact_server_url = artifact_server_url.rstrip("/")
        self.show_hud = show_hud
        
        self.telemetry = GPUTelemetryReporter()
        self.llm = LLMRunner()
        self.current_task_id = None
        self.is_running = True
        self.hud = None

        if self.show_hud:
            self.hud = OverlayHUD(node_id=self.node_id, node_name=f"Node {self.node_id}")
            self.hud.start_hud_thread()

    async def send_heartbeat(self, client: httpx.AsyncClient):
        """Sends periodic heartbeat with GPU and memory telemetry to Raspberry Pi."""
        gpu_data = self.telemetry.get_metrics()
        host_data = self.telemetry.get_host_metrics()
        
        payload = NodeTelemetry(
            node_id=self.node_id,
            name=f"DGX Spark {self.node_id}",
            ip="127.0.0.1",
            status="busy" if self.current_task_id else "online",
            current_task_id=self.current_task_id,
            cpu_percent=host_data["cpu_percent"],
            ram_percent=host_data["ram_percent"],
            gpu=GPUInfo(**gpu_data),
            active_model=self.llm.default_model,
            capabilities=["code_generation", "code_review", "data_analysis"]
        )

        try:
            await client.post(f"{self.coordinator_url}/api/nodes/heartbeat", json=payload.model_dump(), timeout=3.0)
            if self.hud:
                telem_str = f"GPU: {gpu_data['utilization_pct']}% | VRAM: {gpu_data['vram_used_mb']/1024:.1f}/{gpu_data['vram_total_mb']/1024:.0f} GB | {gpu_data['temperature_c']}°C"
                self.hud.update_telemetry(telem_str)
        except Exception:
            pass

    async def execute_task(self, payload: ExecutePayload) -> Dict[str, Any]:
        """Executes a command or LLM task, updating the physical screen HUD and streaming terminal output."""
        task_id = payload.task_id or f"task_{datetime.now().strftime('%H%M%S')}"
        self.current_task_id = task_id

        if self.hud:
            self.hud.update_status("BUSY", task_title=payload.prompt)
            self.hud.append_log(f"\n>>> [TASK {task_id}] Incoming Command from Raspberry Pi:\n>>> Prompt: {payload.prompt}\n")

        print(f"[{self.node_id}] Executing Task {task_id}: {payload.prompt}")
        session = TerminalSession(session_id=task_id)

        # Default shell command if none provided
        target_command = payload.command or f"python3 -c \"print('Executing task: {payload.prompt}'); import time; time.sleep(1); print('Task completed successfully on DGX node.')\""

        captured_stdout = ""
        captured_stderr = ""
        generated_code_file = None

        # Check if local Ollama LLM should be queried
        if not payload.command:
            if self.hud:
                self.hud.append_log(f"[{self.node_id}] Querying local model ({self.llm.default_model})...\n")
            llm_text = ""
            async for token in self.llm.generate_response(payload.prompt):
                llm_text += token
                if self.hud:
                    self.hud.append_log(token)
            captured_stdout = llm_text

            # If model produced python code, save to local workspace file
            if "```python" in llm_text:
                os.makedirs("./workspace", exist_ok=True)
                code_content = llm_text.split("```python")[1].split("```")[0].strip()
                generated_code_file = f"./workspace/{task_id}_output.py"
                with open(generated_code_file, "w", encoding="utf-8") as f:
                    f.write(code_content)
                if self.hud:
                    self.hud.append_log(f"\n[FILE SAVED] Saved generated script to: {generated_code_file}\n")
        else:
            async for stream_name, chunk in session.execute_command_stream(payload.command):
                if stream_name == "stdout":
                    captured_stdout += chunk
                else:
                    captured_stderr += chunk
                if self.hud:
                    self.hud.append_log(chunk)
                print(f"[{self.node_id}] {chunk.strip()}")

        # Auto-upload generated file to i7-14700 PC Vault if file exists
        vault_upload_status = "no_file"
        if generated_code_file and os.path.exists(generated_code_file):
            try:
                fname = os.path.basename(generated_code_file)
                upload_url = f"{self.artifact_server_url}/api/storage/{self.node_id}/upload/{task_id}"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    with open(generated_code_file, "rb") as uf:
                        files = {"file": (fname, uf, "text/plain")}
                        data = {"stage": "outputs"}
                        res = await client.post(upload_url, files=files, data=data)
                        if res.status_code == 200:
                            vault_upload_status = "synced_to_i7_vault"
                            if self.hud:
                                self.hud.append_log(f"[VAULT SYNC] Successfully uploaded to i7 PC: {fname}\n")
            except Exception as e:
                vault_upload_status = f"upload_error: {str(e)}"

        # If Pi dictated a Google Drive upload command, execute it now
        drive_status = "not_requested"
        if payload.dictated_upload_cmd:
            if self.hud:
                self.hud.append_log(f"\n[STORAGE] Executing dictated Drive upload:\n$ {payload.dictated_upload_cmd}\n")
            upload_session = TerminalSession(session_id=f"{task_id}_upload")
            async for _, chk in upload_session.execute_command_stream(payload.dictated_upload_cmd):
                if self.hud:
                    self.hud.append_log(chk)
            drive_status = "upload_success" if upload_session.exit_code == 0 else "upload_failed"

        self.current_task_id = None
        if self.hud:
            self.hud.update_status("ONLINE", task_title="Idle")
            self.hud.append_log(f"\n[Task {task_id} Completed]\n")

        exit_code = 0 if not payload.command else session.exit_code
        result = {
            "status": "success" if exit_code == 0 else "error",
            "task_id": task_id,
            "node_id": self.node_id,
            "exit_code": exit_code,
            "stdout": captured_stdout,
            "stderr": captured_stderr,
            "generated_file": generated_code_file,
            "vault_status": vault_upload_status,
            "drive_status": drive_status,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }

        # If callback URL provided, notify Raspberry Pi
        if payload.callback_url:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(payload.callback_url, json=result)
            except Exception:
                pass

        return result

def create_node_app(agent: DGXNodeAgent) -> FastAPI:
    app = FastAPI(title=f"AEGIS Node Agent - {agent.node_id}")

    @app.get("/api/health")
    def health():
        return {
            "status": "online",
            "node_id": agent.node_id,
            "current_task": agent.current_task_id,
            "gpu": agent.telemetry.get_metrics()
        }

    @app.post("/api/execute")
    async def execute(payload: ExecutePayload):
        return await agent.execute_task(payload)

    return app

async def run_agent_and_server(agent: DGXNodeAgent):
    app = create_node_app(agent)
    config = uvicorn.Config(app, host="0.0.0.0", port=agent.port, log_level="info")
    server = uvicorn.Server(config)

    async def heartbeat_loop():
        async with httpx.AsyncClient() as client:
            while agent.is_running:
                await agent.send_heartbeat(client)
                await asyncio.sleep(5)

    await asyncio.gather(
        server.serve(),
        heartbeat_loop()
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS DGX Node Agent")
    parser.add_argument("--id", type=str, default="dgx-node-1", help="Node ID (e.g., dgx-node-1)")
    parser.add_argument("--port", type=int, default=8801, help="Node HTTP Port (default: 8801)")
    parser.add_argument("--coordinator", type=str, default="http://100.106.207.27:9000", help="AEGIS Coordinator URL")
    parser.add_argument("--artifact-server", type=str, default="http://100.88.197.6:9080", help="Shared Artifact Server URL")
    parser.add_argument("--hud", action="store_true", help="Display desktop overlay HUD on physical screen")
    args = parser.parse_args()

    agent = DGXNodeAgent(node_id=args.id, port=args.port, coordinator_url=args.coordinator, artifact_server_url=args.artifact_server, show_hud=args.hud)
    try:
        asyncio.run(run_agent_and_server(agent))
    except KeyboardInterrupt:
        print("\nNode agent shutting down.")
