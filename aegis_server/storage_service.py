"""AEGIS Shared Storage & Vault Service (Runs on i7-14700 PC - LABG418PC12).
Manages isolated storage vaults for all 8 DGX nodes, coordinates inter-node file handoffs,
and hosts the Mission Control dashboard.
"""
import os
import shutil
import aiofiles
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

VAULT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aegis_storage_vault"))
DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "dashboard"))

# Ensure per-node folders exist
for i in range(1, 9):
    nid = f"dgx-node-{i}"
    for sub in ["workspaces", "outputs", "logs"]:
        os.makedirs(os.path.join(VAULT_ROOT, nid, sub), exist_ok=True)
os.makedirs(os.path.join(VAULT_ROOT, "shared_context"), exist_ok=True)
os.makedirs(DASHBOARD_DIR, exist_ok=True)

app = FastAPI(title="AEGIS Cluster Storage Vault", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/storage/{node_id}/upload/{task_id}")
async def upload_node_file(node_id: str, task_id: str, file: UploadFile = File(...), stage: str = Form("outputs")):
    """Uploads a generated file or script from a specific DGX node into its dedicated vault."""
    target_dir = os.path.join(VAULT_ROOT, node_id, stage, task_id)
    os.makedirs(target_dir, exist_ok=True)
    
    dest_path = os.path.join(target_dir, file.filename)
    async with aiofiles.open(dest_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)

    return {
        "status": "stored_in_vault",
        "node_id": node_id,
        "task_id": task_id,
        "filename": file.filename,
        "size_bytes": len(content),
        "vault_path": f"{node_id}/{stage}/{task_id}/{file.filename}",
        "download_url": f"/api/storage/{node_id}/download/{task_id}/{file.filename}?stage={stage}"
    }

@app.get("/api/storage/{node_id}/download/{task_id}/{filename}")
def download_node_file(node_id: str, task_id: str, filename: str, stage: str = "outputs"):
    """Serves a file stored in a DGX node's vault."""
    fpath = os.path.join(VAULT_ROOT, node_id, stage, task_id, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Requested file not found in node vault.")
    return FileResponse(fpath, filename=filename)

@app.get("/api/storage/{node_id}/files")
def list_node_files(node_id: str):
    """Lists all files stored for a specific DGX node across workspaces and outputs."""
    node_dir = os.path.join(VAULT_ROOT, node_id)
    if not os.path.exists(node_dir):
        return {"node_id": node_id, "files": []}

    file_list = []
    for root, _, files in os.walk(node_dir):
        for f in files:
            full_p = os.path.join(root, f)
            rel_p = os.path.relpath(full_p, node_dir)
            stat = os.stat(full_p)
            file_list.append({
                "filename": f,
                "relative_path": rel_p,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            })
    return {"node_id": node_id, "total_files": len(file_list), "files": file_list}

@app.post("/api/storage/handoff/{from_node}/{to_node}/{task_id}")
def handoff_files_between_nodes(from_node: str, to_node: str, task_id: str, filename: str):
    """Copies a file from from_node's output directly into to_node's incoming workspace for review/testing."""
    src = os.path.join(VAULT_ROOT, from_node, "outputs", task_id, filename)
    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail=f"Source file {filename} not found in {from_node} outputs.")

    dst_dir = os.path.join(VAULT_ROOT, to_node, "workspaces", task_id)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, filename)

    shutil.copy2(src, dst)
    return {
        "status": "handoff_synced",
        "from_node": from_node,
        "to_node": to_node,
        "task_id": task_id,
        "filename": filename,
        "ready_for_review_path": f"{to_node}/workspaces/{task_id}/{filename}"
    }

@app.get("/api/storage/vault/overview")
def get_vault_overview():
    """Summary of all 8 node vaults on this i7-14700 PC."""
    overview = {}
    for i in range(1, 9):
        nid = f"dgx-node-{i}"
        ndir = os.path.join(VAULT_ROOT, nid)
        fcount = sum(len(files) for _, _, files in os.walk(ndir))
        overview[nid] = {"file_count": fcount, "vault_status": "active"}
    return {"vault_root": VAULT_ROOT, "nodes": overview}

@app.get("/api/storage/recent")
def get_recent_artifacts(limit: int = 20):
    """Returns recent files uploaded to the vault across all nodes."""
    recent = []
    for root, dirs, files in os.walk(VAULT_ROOT):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, VAULT_ROOT).replace("\\", "/")
            parts = rel_path.split("/")
            if len(parts) >= 4 and parts[1] == "outputs":
                node_id, stage, task_id, filename = parts[0], parts[1], parts[2], parts[3]
                stat = os.stat(full_path)
                recent.append({
                    "node_id": node_id,
                    "task_id": task_id,
                    "filename": filename,
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "url": f"/api/storage/{node_id}/download/{task_id}/{filename}?stage=outputs"
                })
    recent.sort(key=lambda x: x["modified_at"], reverse=True)
    return {"recent_artifacts": recent[:limit]}

@app.get("/setup")
@app.get("/setup.sh")
@app.get("/dgx_setup.sh")
def get_standalone_setup():
    """Serves dgx_setup.sh (dgx-node-1)."""
    return _serve_setup_file(1)

@app.get("/setup/{node_num}")
def get_standalone_setup_by_num(node_num: int):
    """Serves the setup script for any node (1-8).
    Usage on DGX: curl -fsSL http://100.88.197.6:9080/setup/2 | bash
    """
    if node_num < 1 or node_num > 8:
        raise HTTPException(status_code=400, detail=f"Invalid node number {node_num}. Must be 1-8.")
    return _serve_setup_file(node_num)

# Backward compat shortcuts: /setup2, /setup3, etc.
@app.get("/setup2")
@app.get("/dgx_setup2.sh")
def get_setup_node2(): return _serve_setup_file(2)
@app.get("/setup3")
@app.get("/dgx_setup3.sh")
def get_setup_node3(): return _serve_setup_file(3)
@app.get("/setup4")
@app.get("/dgx_setup4.sh")
def get_setup_node4(): return _serve_setup_file(4)
@app.get("/setup5")
@app.get("/dgx_setup5.sh")
def get_setup_node5(): return _serve_setup_file(5)
@app.get("/setup6")
@app.get("/dgx_setup6.sh")
def get_setup_node6(): return _serve_setup_file(6)
@app.get("/setup7")
@app.get("/dgx_setup7.sh")
def get_setup_node7(): return _serve_setup_file(7)
@app.get("/setup8")
@app.get("/dgx_setup8.sh")
def get_setup_node8(): return _serve_setup_file(8)

def _serve_setup_file(node_num: int):
    """Reads the dedicated dgx_setupN.sh file for the given node number."""
    filename = "dgx_setup.sh" if node_num == 1 else f"dgx_setup{node_num}.sh"
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content, media_type="text/plain")

@app.get("/install.sh")
def get_install_script():
    """Serves the full installer bash script for remote DGX Spark nodes."""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aegis_node", "setup_dgx_oneclick.sh"))
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Installer script not found")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content, media_type="text/plain")


@app.get("/aegis_bundle.tar.gz")
def get_aegis_bundle():
    """Serves the packaged code archive (aegis_node, aegis_core, config) for one-click setup."""
    bundle_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "aegis_bundle.tar.gz"))
    import tarfile
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with tarfile.open(bundle_path, "w:gz") as tar:
        tar.add(os.path.join(root_dir, "aegis_node"), arcname="aegis_node")
        tar.add(os.path.join(root_dir, "aegis_core"), arcname="aegis_core")
        tar.add(os.path.join(root_dir, "config"), arcname="config")
    return FileResponse(bundle_path, media_type="application/gzip", filename="aegis_bundle.tar.gz")

@app.get("/dgx_agent.py")
def get_standalone_dgx_agent():
    """Serves the standalone, single-file DGX node agent (zero dependencies)."""
    agent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aegis_node", "dgx_agent.py"))
    if not os.path.exists(agent_path):
        raise HTTPException(status_code=404, detail="dgx_agent.py not found")
    with open(agent_path, "r", encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content, media_type="text/x-python")

@app.get("/dynamic_hud.py")
def get_dynamic_hud():
    """Serves the Parakeet AI Neon Green Dynamic Island & Corner HUD module."""
    hud_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aegis_node", "overlay", "dynamic_hud.py"))
    if not os.path.exists(hud_path):
        raise HTTPException(status_code=404, detail="dynamic_hud.py not found")
    with open(hud_path, "r", encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content, media_type="text/x-python")

# Dashboard static files mount
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

