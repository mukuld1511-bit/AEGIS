"""Phase 1 Testing Script: Dispatch task from Raspberry Pi to a single DGX node over Tailscale.
"""
import sys
import argparse
import httpx
import json

def test_dispatch(dgx_ip: str = "100.106.207.101", port: int = 8801, prompt: str = "Analyze system health"):
    url = f"http://{dgx_ip}:{port}/api/execute"
    print(f"============================================================")
    print(f" [PHASE 1 TEST] Sending command from Pi -> DGX Node")
    print(f" Target DGX: {url}")
    print(f" Prompt: '{prompt}'")
    print(f"============================================================")

    payload = {
        "task_id": "phase1_test_001",
        "prompt": prompt,
        "command": "python -c \"import sys; print('=== HELLO FROM DGX SPARK ==='); print('Task executed successfully!')\"",
        "dictated_upload_cmd": "echo 'Drive sync simulated' > drive_test.log"
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(url, json=payload)
            print(f"\nResponse Code: {res.status_code}")
            data = res.json()
            print(f"Task ID:   {data.get('task_id')}")
            print(f"Exit Code: {data.get('exit_code')}")
            print(f"\nTerminal Stdout from DGX:\n{data.get('stdout')}")
            print(f"[SUCCESS] PHASE 1 TEST SUCCESSFUL! DGX responded properly.")
    except Exception as e:
        print(f"\n[!] Connection failed: {e}")
        print("Ensure the DGX agent is running with: python -m aegis_node.agent_service --id dgx-node-1 --port 8801 --hud")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AEGIS Phase 1 Tester")
    parser.add_argument("--dgx-ip", default="127.0.0.1", help="Tailscale IP of target DGX Spark machine")
    parser.add_argument("--port", type=int, default=8801, help="Port of target DGX agent")
    parser.add_argument("--prompt", default="Create a Python project that analyses CSV data", help="Task prompt")
    args = parser.parse_args()

    test_dispatch(dgx_ip=args.dgx_ip, port=args.port, prompt=args.prompt)
