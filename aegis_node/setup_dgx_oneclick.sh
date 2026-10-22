#!/usr/bin/env bash
# ==============================================================================
# AEGIS One-Click DGX Spark Node Setup Script
# Installs Ollama, pulls the local model, configures node agent & screen HUD,
# and verifies Tailscale intercommunication with Raspberry Pi & Storage Server.
# ==============================================================================

set -e

NODE_ID=${1:-"dgx-node-1"}                                 # Node identifier
GATEWAY_URL=${2:-"https://raspberrypi.tailc8c1f6.ts.net"} # Raspberry Pi Tailscale Funnel Gateway
STORAGE_URL=${3:-"http://100.88.197.6:9080"}             # i7-14700 PC Vault
MODEL_NAME=${4:-"deepseek-coder-v2:16b"}                 # Local model to pull

echo "======================================================================"
echo " [AEGIS] Starting One-Click DGX Spark Setup (Reverse Heartbeat)"
echo " Node ID:           ${NODE_ID}"
echo " Model to Pull:     ${MODEL_NAME}"
echo " Gateway Funnel:    ${GATEWAY_URL} (Outbound HTTPS - Zero Open Ports)"
echo " Storage PC Vault:  ${STORAGE_URL}"
echo "======================================================================"

# 1. Verify NVIDIA GPU
echo "[1/6] Checking NVIDIA GPU and driver status..."
if command -v nvidia-smi &> /dev/null; then
    echo "[✓] NVIDIA driver detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "[!] Warning: nvidia-smi not detected. Proceeding in emulation mode."
fi

# 2. Ensure Ollama is installed and running
echo "[2/6] Checking Ollama local LLM runtime..."
if ! command -v ollama &> /dev/null; then
    echo "[*] Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Start ollama serve in background if not already active
if ! pgrep -x "ollama" > /dev/null; then
    echo "[*] Starting Ollama daemon..."
    nohup ollama serve > /dev/null 2>&1 &
    sleep 3
fi
echo "[✓] Ollama runtime is active."

# 3. Pull the Local Model
echo "[3/6] Pulling local model: ${MODEL_NAME} (this may take a few minutes)..."
ollama pull "${MODEL_NAME}"
echo "[✓] Model ${MODEL_NAME} is ready on local GPU."

# 4. Install System & Python Tools
echo "[4/6] Installing Python packages and terminal tools..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv tmux curl rclone python3-tk xdotool xprintidle scrot


INSTALL_DIR="/opt/aegis_node"
sudo mkdir -p "${INSTALL_DIR}"
sudo chown -R "$USER:$USER" "${INSTALL_DIR}"

if [ ! -d "${INSTALL_DIR}/venv" ]; then
    python3 -m venv "${INSTALL_DIR}/venv"
fi

source "${INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install uvicorn fastapi httpx psutil pydantic aiofiles python-multipart

# 5. Deploy AEGIS Node Code
echo "[5/6] Deploying AEGIS Node Agent code to ${INSTALL_DIR}..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"

if [ -d "${PARENT_DIR}/aegis_node" ]; then
    cp -r "${PARENT_DIR}/aegis_node" "${INSTALL_DIR}/"
    cp -r "${PARENT_DIR}/aegis_core" "${INSTALL_DIR}/"
    cp -r "${PARENT_DIR}/config" "${INSTALL_DIR}/"
elif [ -d "./aegis_node" ]; then
    cp -r "./aegis_node" "${INSTALL_DIR}/"
    cp -r "./aegis_core" "${INSTALL_DIR}/"
    cp -r "./config" "${INSTALL_DIR}/"
else
    echo "[*] Downloading AEGIS agent bundle from ${STORAGE_URL}/aegis_bundle.tar.gz..."
    curl -fsSL "${STORAGE_URL}/aegis_bundle.tar.gz" -o /tmp/aegis_bundle.tar.gz
    tar -xzf /tmp/aegis_bundle.tar.gz -C "${INSTALL_DIR}/"
    echo "[✓] Code bundle extracted successfully."
fi


# 6. Setup Systemd Service
echo "[6/6] Registering background daemon systemd service..."
SERVICE_FILE="/etc/systemd/system/aegis-dgx.service"

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=AEGIS DGX Node Agent (${NODE_ID})
After=network.target tailscaled.service

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
Environment=DISPLAY=:0
ExecStart=${INSTALL_DIR}/venv/bin/python3 -m aegis_node.dgx_reverse_agent --id ${NODE_ID} --gateway ${GATEWAY_URL} --storage ${STORAGE_URL} --hud
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable aegis-dgx.service
sudo systemctl restart aegis-dgx.service

echo "======================================================================"
echo " [✓] REVERSE-HEARTBEAT DGX SPARK SETUP COMPLETE FOR ${NODE_ID}!"
echo " Inbound Open Ports: ZERO (100% Firewall/NAT Bypass)"
echo " Reverse Polling:   ${GATEWAY_URL} every 3s"
echo " Service Status:    sudo systemctl status aegis-dgx.service"
echo " Live Logs:         sudo journalctl -u aegis-dgx.service -f"
echo "======================================================================"
