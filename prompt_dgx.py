#!/usr/bin/env python3
"""AEGIS Prompt & Storage Vault CLI tool."""
import os
import sys
import glob
import json
import urllib.request

GATEWAY_URL = "https://raspberrypi.tailc8c1f6.ts.net/api/command"
TARGET_PC = "dgx-node-1"
VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aegis_storage_vault", TARGET_PC, "outputs")

def list_vault_files():
    print(f"\n[*] Files stored in Central Vault for {TARGET_PC}:")
    pattern = os.path.join(VAULT_DIR, "**", "*.*")
    files = [f for f in glob.glob(pattern, recursive=True) if os.path.isfile(f)]
    if not files:
        print("    (No files vaulted yet)")
        return
    for idx, f in enumerate(sorted(files, key=os.path.getmtime, reverse=True), 1):
        rel = os.path.relpath(f, VAULT_DIR)
        size = os.path.getsize(f)
        print(f"  {idx}. {rel}  ({size} bytes)")
    print()

def show_last_file():
    pattern = os.path.join(VAULT_DIR, "**", "*.*")
    files = [f for f in glob.glob(pattern, recursive=True) if os.path.isfile(f)]
    if not files:
        print("\n[!] No files found in vault yet.\n")
        return
    latest = max(files, key=os.path.getmtime)
    print(f"\n==================================================================")
    print(f" Latest Vaulted File: {os.path.relpath(latest, VAULT_DIR)}")
    print(f" Full Path: {latest}")
    print(f"==================================================================")
    try:
        with open(latest, "r", encoding="utf-8", errors="ignore") as f:
            print(f.read())
    except Exception as e:
        print(f"[!] Error reading file: {e}")
    print(f"==================================================================\n")

def dispatch(prompt_text: str, target: str = TARGET_PC):
    payload = {
        "pc_id": target,
        "command": prompt_text
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GATEWAY_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"[OK] Dispatched to {target.upper()} via Raspberry Pi Gateway:")
            print(f"     Message: {result.get('message')}")
            print(f"     Status:  {result.get('status')}")
            print(f"\n--> Watch DGX physical monitor (:0 or :1) Dynamic HUD enlarge & stream in real-time!")
    except Exception as e:
        print(f"[!] Error dispatching prompt: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg in ["--list", "-l", "list"]:
            list_vault_files()
            sys.exit(0)
        elif arg in ["--last", "-v", "last", "view"]:
            show_last_file()
            sys.exit(0)
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "Write a complete Python module math_utils.py containing factorial, is_prime, and fibonacci functions with unit tests."
    print(f"[*] Prompting DGX Node: \"{prompt}\"")
    dispatch(prompt)
