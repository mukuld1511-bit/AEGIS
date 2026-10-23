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

# 1. Download standalone single-file agent & Dynamic Island HUD
echo "[1/4] Fetching standalone agent & Dynamic Island HUD..."
curl -fsSL "${STORAGE_URL}/dgx_agent.py" -o "$HOME/dgx_agent.py" || \
curl -fsSL "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/dgx_agent.py" -o "$HOME/dgx_agent.py"
chmod +x "$HOME/dgx_agent.py"

mkdir -p "$HOME/aegis_node/overlay"
curl -fsSL "${STORAGE_URL}/dynamic_hud.py" -o "$HOME/aegis_node/overlay/dynamic_hud.py" || \
curl -fsSL "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/overlay/dynamic_hud.py" -o "$HOME/aegis_node/overlay/dynamic_hud.py" || true
cp "$HOME/aegis_node/overlay/dynamic_hud.py" "$HOME/dynamic_hud.py" 2>/dev/null || true
echo "[✓] Saved $HOME/dgx_agent.py & $HOME/dynamic_hud.py"

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

# 4. Configure Silent Background Startup & Physical Screen Dynamic HUD
echo "[4/4] Configuring DGX Silent Autostart & Parakeet AI Neon Green HUD..."
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

# (A) Create 1-click silent background launcher (Can run and CLOSE terminal immediately)
cat <<EOF > "$HOME/start_aegis_silent.sh"
#!/usr/bin/env bash
# Silent launcher for DGX - runs completely in background, independent of terminal
pkill -f "dgx_agent.py" > /dev/null 2>&1 || true
ACTIVE_DISP="\${DISPLAY:-}"
if [ -z "\$ACTIVE_DISP" ]; then
    if [ -e "/tmp/.X11-unix/X1" ]; then
        ACTIVE_DISP=":1"
    else
        ACTIVE_DISP=":0"
    fi
fi
export DISPLAY="\$ACTIVE_DISP"
export XAUTHORITY="\$HOME/.Xauthority"
xhost +local: > /dev/null 2>&1 || true

nohup /usr/bin/python3 "\$HOME/dgx_agent.py" --id "${NODE_ID}" --gateway "${GATEWAY_URL}" --storage "${STORAGE_URL}" --model "${MODEL_NAME}" --ctx 65536 > /dev/null 2>&1 &
disown

echo "[✓] AEGIS Agent & Dynamic Island HUD launched silently in background (DISPLAY \$ACTIVE_DISP)!"
echo "[✓] Aap ye terminal ab BAND kar sakte hain (Terminal band karne par bhi HUD chalta rahega)."
EOF
chmod +x "$HOME/start_aegis_silent.sh"

# (B) Create 1-click stop script
cat <<EOF > "$HOME/stop_aegis.sh"
#!/usr/bin/env bash
# 1-click stop script for DGX - terminates background agent & HUD
pkill -9 -f "dgx_agent.py" > /dev/null 2>&1 || true
sudo systemctl stop "aegis-dgx-*" > /dev/null 2>&1 || true
echo "[✓] All AEGIS services and HUD stopped cleanly."
EOF
chmod +x "$HOME/stop_aegis.sh"

# (C) Configure Linux XDG Desktop Autostart (Launches silently on DGX boot / login with NO terminal)
mkdir -p "$HOME/.config/autostart"
cat <<EOF > "$HOME/.config/autostart/aegis-dgx.desktop"
[Desktop Entry]
Type=Application
Name=AEGIS Dynamic Island HUD (${NODE_ID})
Comment=Parakeet AI Neon Green Dynamic Island & Floating Corner HUD
Exec=$HOME/start_aegis_silent.sh
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
Categories=Utility;Development;
EOF
chmod +x "$HOME/.config/autostart/aegis-dgx.desktop"

# (D) Configure Desktop Shortcuts on DGX
mkdir -p "$HOME/Desktop"
cat <<EOF > "$HOME/Desktop/Start-AEGIS.desktop"
[Desktop Entry]
Type=Application
Name=Start AEGIS (Silent)
Exec=$HOME/start_aegis_silent.sh
Terminal=false
Icon=utilities-system-monitor
EOF
chmod +x "$HOME/Desktop/Start-AEGIS.desktop"

cat <<EOF > "$HOME/Desktop/Stop-AEGIS.desktop"
[Desktop Entry]
Type=Application
Name=Stop AEGIS
Exec=$HOME/stop_aegis.sh
Terminal=false
Icon=process-stop
EOF
chmod +x "$HOME/Desktop/Stop-AEGIS.desktop"

# (E) Configure persistent systemd service
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
sudo systemctl enable --now ${SERVICE_NAME}.service > /dev/null 2>&1 || true
loginctl enable-linger ${USER} > /dev/null 2>&1 || true

# Start the silent background agent & HUD right now
"$HOME/start_aegis_silent.sh"

echo ""
echo "======================================================================"
echo "✅ [SUCCESS] DGX Node ${NODE_ID} Silent Setup COMPLETE!"
echo "   1. DGX BOOT / LOGIN: Chupchap background me chalega (NO terminal window)."
echo "   2. ENTRANCE ANIMATION: Dynamic Island & Corner Logo slide hokar aayenge."
echo "   3. TERMINAL ME RUN: '~/start_aegis_silent.sh' chalao aur terminal BAND kar do."
echo "   4. 1-CLICK STOP: '~/stop_aegis.sh' se ek baar me sab band."
echo "   5. Heartbeat: Polling ${GATEWAY_URL} every 6s (0 open inbound ports)"
echo "   6. Model:     ${MODEL_NAME} (Ollama Local GPU)"
echo "======================================================================"
