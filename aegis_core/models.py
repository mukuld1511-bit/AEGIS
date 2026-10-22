"""Data models for AEGIS Core, Nodes, and Storage Services.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

class GPUInfo(BaseModel):
    name: str = "Unknown GPU"
    vram_used_mb: float = 0.0
    vram_total_mb: float = 81920.0 # 80GB DGX standard
    utilization_pct: float = 0.0
    temperature_c: float = 0.0

class NodeTelemetry(BaseModel):
    node_id: str
    name: str
    ip: str
    status: str = "online" # online, busy, offline, quarantined
    current_task_id: Optional[str] = None
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    gpu: GPUInfo = Field(default_factory=GPUInfo)
    active_model: str = ""
    capabilities: List[str] = Field(default_factory=list)
    active_window: Optional[str] = ""
    idle_time_seconds: float = 0.0
    screenshot_b64: Optional[str] = None
    client_type: str = "dgx" # dgx or lab_pc
    os_platform: str = "linux" # linux or windows
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HeartbeatCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: f"cmd-{uuid.uuid4().hex[:8]}")
    node_id: str
    command_type: str # warn, lock, unlock, shutdown, capture, execute_task, run_command, pull_model
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CommandResult(BaseModel):
    command_id: str
    node_id: str
    status: str = "completed" # completed, failed
    exit_code: int = 0
    output: str = ""
    error: str = ""
    screenshot_b64: Optional[str] = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TaskStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_index: int = 1
    node_id: str
    description: str
    command: Optional[str] = None
    status: str = "running" # running, completed, failed, awaiting_approval
    stdout: str = ""
    stderr: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

class TaskArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    filename: str
    file_path: str
    size_bytes: int
    content_type: str = "text/plain"
    node_id: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: f"tsk-{uuid.uuid4().hex[:8]}")
    title: str
    prompt: str
    language: str = "hi-en"
    assigned_node_id: str
    reviewer_node_id: Optional[str] = None
    status: str = "queued" # queued, running, awaiting_approval, reviewing, completed, failed
    steps: List[TaskStep] = Field(default_factory=list)
    artifacts: List[TaskArtifact] = Field(default_factory=list)
    result_summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SafetyEvaluation(BaseModel):
    is_safe: bool
    risk_level: str # LOW, MEDIUM, HIGH, CRITICAL
    requires_confirmation: bool
    reasons: List[str] = Field(default_factory=list)
    proposed_command: str = ""

