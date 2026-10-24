#!/usr/bin/env python3
"""AEGIS Remote Control & Execution Utility (scripts/remote_exec_dgx.py).
Dispatches shell commands, model pulls, and tasks to DGX nodes via Reverse Heartbeat Polling.
Zero inbound open ports required on DGX nodes. Works from home or anywhere!

Usage Examples:
    # 1. Update code on all DGX nodes (git pull):
    python scripts/remote_exec_dgx.py --all "cd ~/Aegis && git pull origin main"

    # 2. Update specific node:
    python scripts/remote_exec_dgx.py --node dgx-node-1 "cd ~/Aegis && git pull origin main"

    # 3. Pull a model remotely on Node 2:
    python scripts/remote_exec_dgx.py --node dgx-node-2 --pull-model "qwen2.5-coder:32b"

    # 4. View live status of all nodes:
    python scripts/remote_exec_dgx.py --status
"""
import sys
import os
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_GATEWAYS = [
    "http://localhost:9000",
    "https://labg418pc12.tailc8c1f6.ts.net",
    "https://raspberrypi.tailc8c1f6.ts.net"
]

def get_active_gateway():
    for gw in DEFAULT_GATEWAYS:
        try:
            req = urllib.request.Request(f"{gw}/api/nodes", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return gw
        except Exception:
            continue
    return DEFAULT_GATEWAYS[0]

def show_nodes_status(gw: str):
    url = f"{gw}/api/nodes"
    try:
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            nodes = json.loads(resp.read().decode("utf-8"))
            print(f"\n{'='*75}")
            print(f" AEGIS CLUSTER STATUS (Gateway: {gw})")
            print(f"{'='*75}")
            print(f"{'NODE ID':<14} {'ROLE / NAME':<30} {'STATUS':<10} {'ACTIVE MODEL':<18}")
            print(f"{'-'*75}")
            for n in nodes:
                nid = n.get("node_id", "N/A")
                name = n.get("name", nid)[:28]
                stat = n.get("status", "unknown").upper()
                model = n.get("active_model", "none") or "none"
                hb = n.get("last_heartbeat", "never")
                if hb and "T" in hb:
                    hb_time = hb.split("T")[1].split(".")[0]
                else:
                    hb_time = str(hb)
                print(f"{nid:<14} {name:<30} {stat:<10} {model:<18} (HB: {hb_time})")
            print(f"{'='*75}\n")
    except Exception as e:
        print(f"[!] Error fetching node status: {e}")

def queue_command(gw: str, node_id: str, cmd_type: str, payload: dict):
    url = f"{gw}/api/client/command"
    body = {
        "node_id": node_id,
        "command_type": cmd_type,
        "payload": payload
    }
    data = json.dumps(body).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            print(f"[✓] Queued for {node_id}: {cmd_type.upper()} (CmdID: {res.get('command_id')})")
            return True
    except Exception as e:
        print(f"[!] Failed to queue for {node_id}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="AEGIS Remote Command Dispatcher")
    parser.add_argument("--node", "-n", type=str, default=None, help="Target node ID (e.g. dgx-node-1 or 1)")
    parser.add_argument("--all", "-a", action="store_true", help="Target all nodes (dgx-node-1 to dgx-node-4)")
    parser.add_argument("--pull-model", type=str, default=None, help="Ollama model to pull remotely")
    parser.add_argument("--status", "-s", action="store_true", help="Print live cluster node telemetry & status")
    parser.add_argument("cmd", nargs="?", default=None, help="Shell command to run remotely on DGX")

    args = parser.parse_args()

    gw = get_active_gateway()

    if args.status or (not args.cmd and not args.pull_model and not args.all and not args.node):
        show_nodes_status(gw)
        if not args.cmd and not args.pull_model:
            return

    # Determine targets
    if args.all:
        targets = ["dgx-node-1", "dgx-node-2", "dgx-node-3", "dgx-node-4"]
    elif args.node:
        n = args.node.strip()
        if n.isdigit():
            targets = [f"dgx-node-{n}"]
        elif not n.startswith("dgx-node-"):
            targets = [f"dgx-node-{n}"]
        else:
            targets = [n]
    else:
        targets = ["dgx-node-1"]

    # Dispatch
    for target in targets:
        if args.pull_model:
            print(f"[*] Queueing model pull for {target}: {args.pull_model}")
            queue_command(gw, target, "pull_model", {"model": args.pull_model})
        elif args.cmd:
            print(f"[*] Queueing shell command for {target}: {args.cmd}")
            queue_command(gw, target, "run_command", {"command": args.cmd})

    print(f"\n[OK] Commands queued successfully!")
    print(f"--> Target nodes will execute on their next 6-second heartbeat poll.")
    print(f"--> You do NOT need physical terminal access on DGX machines.\n")

if __name__ == "__main__":
    main()
