#!/usr/bin/env python3
"""AEGIS Prompt & Storage Vault CLI tool.
Easily prompt any DGX node from terminal.
Usage:
    python prompt_dgx.py "your prompt here"
    python prompt_dgx.py --node 2 "review this code"
    python prompt_dgx.py --node dgx-node-1 "write a script"
    python prompt_dgx.py --list
    python prompt_dgx.py --last
"""
import os
import sys
import glob
import json
import urllib.request
import urllib.error

from typing import Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

URLS = [
    "http://localhost:9000/api/command",
    "https://raspberrypi.tailc8c1f6.ts.net/api/command",
    "https://labg418pc12.tailc8c1f6.ts.net:8443/api/command"
]

DEFAULT_NODE = "dgx-node-1"

def list_vault_files(node_id: str = DEFAULT_NODE):
    vault_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aegis_storage_vault", node_id, "outputs")
    print(f"\n[*] Files stored in Central Vault for {node_id}:")
    pattern = os.path.join(vault_dir, "**", "*.*")
    files = [f for f in glob.glob(pattern, recursive=True) if os.path.isfile(f)]
    if not files:
        print("    (No files vaulted yet)")
        return
    for idx, f in enumerate(sorted(files, key=os.path.getmtime, reverse=True), 1):
        rel = os.path.relpath(f, vault_dir)
        size = os.path.getsize(f)
        print(f"  {idx}. {rel}  ({size} bytes)")
    print()

def show_last_file(node_id: str = DEFAULT_NODE):
    vault_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aegis_storage_vault", node_id, "outputs")
    pattern = os.path.join(vault_dir, "**", "*.*")
    files = [f for f in glob.glob(pattern, recursive=True) if os.path.isfile(f)]
    if not files:
        print(f"\n[!] No files found in vault yet for {node_id}.\n")
        return
    code_files = [f for f in files if not f.endswith("manifest.json")]
    latest = max(code_files or files, key=os.path.getmtime)
    print(f"\n==================================================================")
    print(f" Latest Vaulted File ({node_id}): {os.path.relpath(latest, vault_dir)}")
    print(f" Full Path: {latest}")
    print(f"==================================================================")
    try:
        with open(latest, "r", encoding="utf-8", errors="ignore") as f:
            print(f.read())
    except Exception as e:
        print(f"[!] Error reading file: {e}")
    print(f"==================================================================\n")

def dispatch(prompt_text: str, target: Optional[str] = None):
    payload = {
        "command": prompt_text,
        "preferred_node": target,
        "pc_id": target
    }
    data = json.dumps(payload).encode("utf-8")
    
    last_err = None
    for url in URLS:
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                task_id = result.get("task_id", "N/A")
                assigned = result.get("assigned_node", target or "dgx-node-1")
                reviewer = result.get("reviewer_node", "N/A")
                status = result.get("status", "success")
                speech = result.get("spoken_response", "")
                text_explanation = result.get("text_response", "")
                code = result.get("result_code")
                filename = result.get("filename")
                vault_path = result.get("vault_path")
                size_bytes = result.get("size_bytes", 0)

                print(f"\n╔══════════════════════════════════════════════════════════════════╗")
                print(f"║  🚀 AEGIS CLUSTER TASK DISPATCHED & PROCESSED                   ")
                print(f"╠══════════════════════════════════════════════════════════════════╣")
                print(f"║  Task ID:       {task_id}                                       ")
                print(f"║  Assigned Node: {assigned.upper()}                              ")
                print(f"║  Reviewer Node: {reviewer.upper()}                              ")
                print(f"║  Status:        {status}                                        ")
                if filename:
                    print(f"║  Generated File:{filename} ({size_bytes} bytes)                 ")
                if vault_path:
                    print(f"║  Vault Storage: aegis_storage_vault/{vault_path}                ")
                print(f"╚══════════════════════════════════════════════════════════════════╝")

                if text_explanation:
                    print(f"\n[AI Solution Explanation & Architecture]:")
                    print(text_explanation)

                if speech:
                    print(f"\n[AI Voice Dictation]: {speech}")

                if code:
                    print(f"\n====================== [GENERATED PYTHON CODE] ======================")
                    print(code)
                    print(f"====================================================================\n")

                print(f"--> DGX Dynamic Island HUD par model GPU stream active ho chuka hai!")
                print(f"--> Local Vault File: aegis_storage_vault/{assigned}/outputs/{task_id}/{filename or ''}\n")
                return
        except Exception as e:
            last_err = e
            continue
            
    print(f"\n[!] Error dispatching prompt: {last_err}\n")

if __name__ == "__main__":
    args = sys.argv[1:]
    target_node = None
    
    # Parse --node or -n
    if "--node" in args:
        idx = args.index("--node")
        if idx + 1 < len(args):
            val = args[idx + 1].strip()
            target_node = f"dgx-node-{val}" if val.isdigit() else val
            args = args[:idx] + args[idx + 2:]
    elif "-n" in args:
        idx = args.index("-n")
        if idx + 1 < len(args):
            val = args[idx + 1].strip()
            target_node = f"dgx-node-{val}" if val.isdigit() else val
            args = args[:idx] + args[idx + 2:]

    if not args:
        prompt = "Write a complete Python module math_utils.py containing factorial, is_prime, and fibonacci functions with unit tests."
    else:
        first = args[0].strip()
        if first in ["--list", "-l", "list"]:
            list_vault_files(target_node or DEFAULT_NODE)
            sys.exit(0)
        elif first in ["--last", "-v", "last", "view"]:
            show_last_file(target_node or DEFAULT_NODE)
            sys.exit(0)
        prompt = " ".join(args)

    if target_node:
        print(f"[*] Prompting {target_node.upper()}: \"{prompt}\"")
    else:
        print(f"[*] Auto-Routing Prompt by Intent: \"{prompt}\"")
    dispatch(prompt, target_node)
