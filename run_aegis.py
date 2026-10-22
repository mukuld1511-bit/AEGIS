"""AEGIS Master Launcher.
Unified CLI entry point to start the Central Coordinator, i7-14700 Storage Server, or Node Agents.
"""
import sys
import os
import argparse
import uvicorn
import asyncio
import threading

# Add workspace to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from aegis_core.state_manager import StateManager
from aegis_core.safety_guard import SafetyGuard
from aegis_core.voice.dialogue_manager import DialogueManager
from aegis_core.orchestrator import Orchestrator
from aegis_core.api.server import create_app as create_core_app
from aegis_server.storage_service import app as storage_app

def start_core(host="0.0.0.0", port=9000):
    """Starts the AEGIS Central Coordinator on the Raspberry Pi or local system."""
    print(f"===========================================================")
    print(f" [AEGIS CORE] Starting Coordinator on http://{host}:{port}")
    print(f" Voice engine, node routing, and safety guard active.")
    print(f"===========================================================")
    
    state_mgr = StateManager(nodes_config_path="config/nodes.json")
    safety = SafetyGuard()
    dialogue = DialogueManager()
    orchestrator = Orchestrator(state_mgr, safety, dialogue)
    
    app = create_core_app(state_mgr, orchestrator, safety)
    uvicorn.run(app, host=host, port=port, log_level="info")

def start_storage(host="0.0.0.0", port=9080):
    """Starts the shared artifact server & mission control on this i7-14700 PC."""
    print(f"===========================================================")
    print(f" [AEGIS STORAGE] Starting on http://{host}:{port}")
    print(f" Mission Control UI: http://localhost:{port}/")
    print(f" Shared Vault: ./aegis_server/artifacts/")
    print(f"===========================================================")
    uvicorn.run(storage_app, host=host, port=port, log_level="info")

def start_all(core_port=9000, storage_port=9080):
    """Runs Core Coordinator and i7 Storage Server concurrently."""
    t_core = threading.Thread(target=start_core, kwargs={"port": core_port}, daemon=True)
    t_core.start()

    print("\nStarting i7-14700 Storage Vault & Mission Control...")
    start_storage(port=storage_port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Master Runner")
    parser.add_argument("--core", action="store_true", help="Start Central Coordinator (Pi Control Plane)")
    parser.add_argument("--server", action="store_true", help="Start i7-14700 Shared Storage & Mission Control Dashboard")
    parser.add_argument("--all", action="store_true", help="Start both Core and Storage Server concurrently")
    parser.add_argument("--port", type=int, default=None, help="Custom port override")

    args = parser.parse_args()

    if args.core:
        start_core(port=args.port or 8000)
    elif args.server:
        start_storage(port=args.port or 8080)
    elif args.all or len(sys.argv) == 1:
        # Default behavior: run all components
        start_all()
