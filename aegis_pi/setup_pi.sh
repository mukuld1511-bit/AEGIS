#!/usr/bin/env bash
# ==============================================================================
# AEGIS Raspberry Pi 8GB Central Coordinator Installer Script
# Installs dependencies, rclone, audio drivers, and sets up systemd background service.
# ==============================================================================

set -e

PORT=${1:-9000}
INSTALL_DIR="/opt/aegis_pi"

echo "=========================================================="
echo " Setting up AEGIS Central Hub on Raspberry Pi 8GB"
echo " Coordinator Port: ${PORT}"
echo " Install Directory: ${INSTALL_DIR}"
echo "=========================================================="

# 1. Update OS & install audio, CLI and storage tools
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv rclone alsa-utils espeak-ng tmux curl

# 2. Verify Tailscale
if command -v tailscale &> /dev/null; then
    echo "[✓] Tailscale is installed:"
    tailscale ip -4
else
    echo "[!] Tailscale not detected. Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up
fi

# 3. Setup Virtual Environment
sudo mkdir -p "${INSTALL_DIR}"
sudo chown -R "$USER:$USER" "${INSTALL_DIR}"

if [ ! -d "${INSTALL_DIR}/venv" ]; then
    python3 -m venv "${INSTALL_DIR}/venv"
fi

source "${INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install fastapi uvicorn websockets httpx pydantic aiofiles python-multipart

# 4. Copy Code
echo "[*] Deploying AEGIS core modules to ${INSTALL_DIR}..."
cp -r ../aegis_core "${INSTALL_DIR}/"
cp -r ../aegis_pi "${INSTALL_DIR}/"
cp -r ../config "${INSTALL_DIR}/"
cp ../run_aegis.py "${INSTALL_DIR}/"

# 5. Create Systemd Service for persistent 24/7 background operation
SERVICE_FILE="/etc/systemd/system/aegis-pi.service"
echo "[*] Creating systemd service at ${SERVICE_FILE}..."

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=AEGIS Raspberry Pi Central Coordinator Service
After=network.target tailscaled.service

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 run_aegis.py --core --port ${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable aegis-pi.service
sudo systemctl restart aegis-pi.service

echo "=========================================================="
echo " [✓] AEGIS Raspberry Pi Hub Setup Complete!"
echo " Portal listening on: http://raspberrypi.tailc8c1f6.ts.net:${PORT}"
echo " Check service:       sudo systemctl status aegis-pi.service"
echo "=========================================================="
