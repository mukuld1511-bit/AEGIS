# AEGIS Universal Multi-Node Synchronization Rule

## MANDATORY DIRECTIVE: Complete Parity Across All DGX Nodes (1 to 8)
Whenever any feature, fix, improvement, configuration, or requirement is added or modified for ANY DGX node (e.g. Node 1 or Node 2):
1. **Always apply to ALL nodes by default**: Never apply a change to Node 1 without Node 2, or to Node 2 without Node 1 and nodes 3-8.
2. **Single Shared Standalone Agent (`aegis_node/dgx_agent.py`)**: All nodes run `dgx_agent.py` with their specific `--id dgx-node-N`. All animations, glassmorphism, HUD pop-downs, and communication logic live here and serve all 8 nodes equally.
3. **Setup Scripts Parity (`aegis_server/dgx_setup.sh` to `dgx_setup8.sh`)**:
   - All setup scripts must share the exact same 5-step installer structure:
     - [1/5] Cleanup & directory isolation
     - [2/5] Auto-install system packages & Python requirements (`pip3`, `PyQt5`, `requests`, `psutil`)
     - [3/5] Auto-install Ollama & verify/pull assigned model (`qwen2.5-coder:32b`, etc.)
     - [4/5] Auto-download latest standalone agent (`dgx_agent.py`)
     - [5/5] Detect physical X11 display `:0`, `.Xauthority`, and launch in background
   - Any script update must be synchronized across all `dgx_setup*.sh` files.
