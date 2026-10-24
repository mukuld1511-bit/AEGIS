#!/usr/bin/env bash
# ==============================================================================
# AEGIS Big Flagship Model Downloader for Nodes 1, 2, 3, 4
# ==============================================================================
set -e

NODE_NUM="${1:-all}"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  🚀 AEGIS Flagship Big Model Preparer (DGX Nodes 1 - 4)          "
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Node 1: qwen2.5-coder:32b     (Lead Coder, 32B ~19GB)           "
echo "║  Node 2: qwen2.5-coder:32b     (Reviewer & QA, 32B ~19GB)        "
echo "║  Node 3: llama3.2-vision:90b   (Multimodal Vision, 90B ~55GB)    "
echo "║  Node 4: mixtral:8x22b         (Deep Reasoner MoE, 141B ~79GB)   "
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Ensure Ollama daemon is active
if ! pgrep -f "ollama serve" > /dev/null 2>&1; then
    echo "[*] Starting Ollama daemon..."
    nohup ollama serve > /dev/null 2>&1 &
    sleep 3
fi

pull_model() {
    local m="$1"
    local desc="$2"
    echo "============================================================"
    echo "[*] Pulling ${desc}: ${m} onto DGX GPU..."
    echo "============================================================"
    ollama pull "$m"
    echo "[✓] Successfully verified: ${m}"
    echo ""
}

case "$NODE_NUM" in
    1)
        pull_model "qwen2.5-coder:32b" "Node 1 (Lead Coder)"
        ;;
    2)
        pull_model "qwen2.5-coder:32b" "Node 2 (Reviewer & QA)"
        ;;
    3)
        pull_model "llama3.2-vision:90b" "Node 3 (Flagship Vision 90B)"
        ;;
    4)
        pull_model "mixtral:8x22b" "Node 4 (Deep Reasoner MoE 141B)"
        ;;
    all)
        echo "Pulling models for current machine..."
        # If hostname or folder indicates node number, pull that node's model
        if [[ "$PWD" == *"dgx-node-1"* ]] || [[ "$HOSTNAME" == *"1"* ]]; then
            pull_model "qwen2.5-coder:32b" "Node 1"
        elif [[ "$PWD" == *"dgx-node-2"* ]] || [[ "$HOSTNAME" == *"2"* ]]; then
            pull_model "qwen2.5-coder:32b" "Node 2"
        elif [[ "$PWD" == *"dgx-node-3"* ]] || [[ "$HOSTNAME" == *"3"* ]]; then
            pull_model "llama3.2-vision:90b" "Node 3"
        elif [[ "$PWD" == *"dgx-node-4"* ]] || [[ "$HOSTNAME" == *"4"* ]]; then
            pull_model "mixtral:8x22b" "Node 4"
        else
            echo "Usage: ./pull_big_models.sh [1|2|3|4|all]"
        fi
        ;;
    *)
        echo "Usage: ./pull_big_models.sh [1|2|3|4]"
        exit 1
        ;;
esac
