#!/usr/bin/env python3
"""Convenient CLI tool to dispatch prompts directly to DGX Spark 1 via Raspberry Pi Gateway."""
import sys
import json
import urllib.request

GATEWAY_URL = "https://raspberrypi.tailc8c1f6.ts.net/api/command"
TARGET_PC = "dgx-node-1"

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
            print(f"[✓] Dispatched to {target.upper()} via Raspberry Pi Gateway:")
            print(f"    Message: {result.get('message')}")
            print(f"    Status:  {result.get('status')}")
            print(f"\n--> Watch DGX physical monitor (:0) Floating HUD stream the response in real-time!")
    except Exception as e:
        print(f"[!] Error dispatching prompt: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "Write a complete Python module math_utils.py containing factorial, is_prime, and fibonacci functions with unit tests."
    print(f"[*] Prompting DGX Node: \"{prompt}\"")
    dispatch(prompt)
