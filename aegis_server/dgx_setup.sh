#!/usr/bin/env bash
# ==============================================================================
# AEGIS Standalone DGX Node Auto-Setup (1-Liner)
# Runs directly on remote DGX Spark nodes via Tailscale:
# curl -fsSL http://100.88.197.6:9080/setup | bash
# ==============================================================================
set -e

NODE_ID=${1:-"dgx-node-1"}
STORAGE_URL=${2:-"http://100.88.197.6:9080"}
GATEWAY_URL=${3:-"https://raspberrypi.tailc8c1f6.ts.net"}
MODEL_NAME=${4:-"deepseek-coder-v2:16b"}

echo "======================================================================"
echo "🚀 [AEGIS] 1-Click Auto-Setup for ${NODE_ID}"
echo "   Target Model: ${MODEL_NAME}"
echo "   Storage Vault: ${STORAGE_URL}"
echo "   Gateway Hub:  ${GATEWAY_URL}"
echo "======================================================================"

# 1. Download standalone single-file agent directly from GitHub Raw
echo "[1/4] Fetching standalone agent (dgx_agent.py) from GitHub Raw..."
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
ollama pull "${MODEL_NAME}"
echo "[✓] Model ready: ${MODEL_NAME}"

# 4. Configure auto-restart systemd service with Physical Screen HUD (:0)
echo "[4/4] Activating background daemon with screen overlay HUD (aegis-dgx.service)..."
sudo apt-get update -y > /dev/null 2>&1 || true
sudo apt-get install -y python3-tk > /dev/null 2>&1 || true
xhost +local: > /dev/null 2>&1 || true

SERVICE_FILE="/etc/systemd/system/aegis-dgx.service"

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=AEGIS DGX Node Agent with Floating Screen HUD (${NODE_ID})
After=network.target graphical.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${HOME}
Environment=DISPLAY=:0
Environment=XAUTHORITY=${HOME}/.Xauthority
ExecStart=/usr/bin/python3 ${HOME}/dgx_agent.py --id ${NODE_ID} --gateway ${GATEWAY_URL} --storage ${STORAGE_URL} --model ${MODEL_NAME}
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable --now aegis-dgx.service


echo ""
echo "======================================================================"
echo "✅ [SUCCESS] DGX Node ${NODE_ID} is 100% setup and ACTIVE!"
echo "   Heartbeat: Polling ${GATEWAY_URL} every 6 seconds"
echo "   Model:     ${MODEL_NAME} (Ollama Local GPU)"
echo "   Vault:     Auto-syncing to ${STORAGE_URL}"
echo "   Status:    sudo systemctl status aegis-dgx"
echo "======================================================================"
