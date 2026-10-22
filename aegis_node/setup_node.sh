#!/usr/bin/env bash
# ==============================================================================
# AEGIS DGX Node Installation & Service Setup Script
# Installs Python dependencies, checks NVIDIA drivers, and registers systemd service.
# ==============================================================================

set -e

NODE_ID=${1:-"dgx-node-1"}
COORDINATOR_URL=${2:-"http://100.106.207.27:8000"}
ARTIFACT_SERVER_URL=${3:-"http://100.88.197.6:8080"}

echo "=========================================================="
echo " Setting up AEGIS Node Agent: ${NODE_ID}"
echo " Coordinator: ${COORDINATOR_URL}"
echo " Artifact Server: ${ARTIFACT_SERVER_URL}"
echo "=========================================================="

# 1. Verify NVIDIA Driver & GPU
if command -v nvidia-smi &> /dev/null; then
    echo "[✓] NVIDIA driver detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "[!] Warning: nvidia-smi not detected. Running in emulation mode."
fi

# 2. Ensure Python3 and pip
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv python3-tk tmux

# 3. Create Virtualenv
INSTALL_DIR="/opt/aegis_node"
sudo mkdir -p "${INSTALL_DIR}"
sudo chown -R "$USER:$USER" "${INSTALL_DIR}"

if [ ! -d "${INSTALL_DIR}/venv" ]; then
    python3 -m venv "${INSTALL_DIR}/venv"
fi

source "${INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install httpx psutil pydantic websockets

# 4. Copy Code
echo "[*] Copying node files to ${INSTALL_DIR}..."
cp -r ../aegis_node "${INSTALL_DIR}/"
cp -r ../aegis_core "${INSTALL_DIR}/"

# 5. Create systemd service for persistent background daemon
SERVICE_FILE="/etc/systemd/system/aegis-node.service"
echo "[*] Registering systemd service at ${SERVICE_FILE}..."

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=AEGIS DGX Node Agent (${NODE_ID})
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
Environment=DISPLAY=:0
ExecStart=${INSTALL_DIR}/venv/bin/python3 -m aegis_node.agent_service --id ${NODE_ID} --coordinator ${COORDINATOR_URL} --artifact-server ${ARTIFACT_SERVER_URL} --hud
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable aegis-node.service

echo "=========================================================="
echo " [✓] AEGIS Node Setup Complete for ${NODE_ID}!"
echo " Start service with: sudo systemctl start aegis-node.service"
echo " View status with:   sudo systemctl status aegis-node.service"
echo "=========================================================="
