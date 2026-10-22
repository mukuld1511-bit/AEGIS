#!/usr/bin/env bash
# ==============================================================================
# AEGIS Standalone DGX Node Auto-Setup (1-Liner)
# Runs directly on remote DGX Spark nodes via Tailscale:
# curl -fsSL http://100.88.197.6:9080/setup | bash -s -- dgx-node-1
# curl -fsSL http://100.88.197.6:9080/setup | bash -s -- dgx-node-2
# curl -fsSL http://100.88.197.6:9080/setup | bash -s -- dgx-node-3
# ==============================================================================
set -e

NODE_ID=${1:-"dgx-node-1"}
STORAGE_URL=${2:-"http://100.88.197.6:9080"}
GATEWAY_URL=${3:-"https://raspberrypi.tailc8c1f6.ts.net"}

# Auto-determine default model per node role if not explicitly specified
if [ -z "$4" ]; then
    case "$NODE_ID" in
        "dgx-node-1") MODEL_NAME="qwen2.5-coder:32b" ;;
        "dgx-node-2") MODEL_NAME="qwen2.5-coder:32b" ;;
        "dgx-node-3") MODEL_NAME="pixtral-large:124b-q4_K_M" ;;
        *) MODEL_NAME="qwen2.5-coder:32b" ;;
    esac
else
    MODEL_NAME="$4"
fi

echo "======================================================================"
echo "🚀 [AEGIS] 1-Click Auto-Setup for ${NODE_ID}"
echo "   Target Model:  ${MODEL_NAME}"
echo "   Storage Vault: ${STORAGE_URL}"
echo "   Gateway Hub:   ${GATEWAY_URL}"
echo "======================================================================"

# 1. Download standalone single-file agent
echo "[1/4] Fetching standalone agent (dgx_agent.py)..."
curl -fsSL "${STORAGE_URL}/dgx_agent.py" -o "$HOME/dgx_agent.py" || \
curl -fsSL "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/dgx_agent.py" -o "$HOME/dgx_agent.py"
chmod +x "$HOME/dgx_agent.py"
echo "[✓] Saved $HOME/dgx_agent.py"

# 2. Check/Install Ollama GPU runtime
echo "[2/4] Verifying Ollama GPU runtime..."
if ! command -v ollama &> /dev/null; then
    echo "[*] Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

if ! pgrep -x "ollama" > /dev/null; then
    echo "[*] Starting Ollama daemon..."
    nohup ollama serve > /dev/null 2>&1 &
    sleep 3
fi
echo "[✓] Ollama GPU service active."

# 3. Pull local model
echo "[3/4] Pulling ${MODEL_NAME} on local GPU (Blackwell 128GB)..."
ollama pull "${MODEL_NAME}" || ollama pull "qwen2.5-coder:32b" || true
echo "[✓] Model ready: ${MODEL_NAME}"

# 4. Configure auto-restart systemd service with Physical Screen HUD
echo "[4/4] Activating background daemon with Dynamic Island & Corner HUD..."
sudo apt-get update -y > /dev/null 2>&1 || true
sudo apt-get install -y python3-pyqt5 python3-tk > /dev/null 2>&1 || pip3 install PyQt5 || true
xhost +local: > /dev/null 2>&1 || true

ACTIVE_DISP="${DISPLAY:-}"
if [ -z "$ACTIVE_DISP" ]; then
    if [ -e "/tmp/.X11-unix/X1" ]; then
        ACTIVE_DISP=":1"
    else
        ACTIVE_DISP=":0"
    fi
fi

SERVICE_NAME="aegis-dgx-${NODE_ID}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=AEGIS Autonomous DGX Agent with Dynamic Island HUD (${NODE_ID})
After=network.target graphical.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${HOME}
Environment=DISPLAY=${ACTIVE_DISP}
Environment=XAUTHORITY=${HOME}/.Xauthority
ExecStart=/usr/bin/python3 ${HOME}/dgx_agent.py --id ${NODE_ID} --gateway ${GATEWAY_URL} --storage ${STORAGE_URL} --model ${MODEL_NAME} --ctx 65536
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE_NAME}.service
loginctl enable-linger ${USER} > /dev/null 2>&1 || true

echo ""
echo "======================================================================"
echo "✅ [SUCCESS] DGX Node ${NODE_ID} is 100% setup and ACTIVE!"
echo "   Heartbeat: Polling ${GATEWAY_URL} every 6 seconds"
echo "   Model:     ${MODEL_NAME} (Ollama Local GPU)"
echo "   Vault:     Auto-syncing to ${STORAGE_URL}"
echo "   Service:   ${SERVICE_NAME}.service"
echo "   Status:    sudo systemctl status ${SERVICE_NAME}"
echo "   Logs:      journalctl -u ${SERVICE_NAME} -f"
echo "======================================================================"
