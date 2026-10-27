#!/usr/bin/env bash
# ==============================================================================
# AEGIS Standalone DGX Node 3 Setup & Launcher (From Scratch)
# Node: dgx-node-3 (Multimodal Vision)
# ==============================================================================
set -e
cd "$HOME"

NODE_ID="dgx-node-3"
ROLE="Multimodal Vision"
GATEWAY_URL="https://raspberrypi.tailc8c1f6.ts.net"
STORAGE_URL="https://labg418pc12.tailc8c1f6.ts.net:8443"
MODEL_NAME="llama3.2-vision:11b"

AEGIS_DIR="$HOME/aegis/${NODE_ID}"
AGENT_FILE="$AEGIS_DIR/dgx_agent.py"
LOG_FILE="$AEGIS_DIR/agent.log"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  🚀 AEGIS DGX Node 3 Setup & Launcher (${ROLE})                 "
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Node ID:   ${NODE_ID}                                         "
echo "║  Directory: ${AEGIS_DIR}                                       "
echo "║  Gateway:   ${GATEWAY_URL}                                      "
echo "║  Vault:     ${STORAGE_URL}                                      "
echo "║  Model:     ${MODEL_NAME}                                       "
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Stop conflicting agent processes & prepare workspace directory
echo "[1/5] Stopping any existing processes & preparing workspace..."
pkill -9 -f "dgx_agent" > /dev/null 2>&1 || true
sleep 1
mkdir -p "$AEGIS_DIR/workspace"

# 2. Check apps & Python requirements (PyQt5, requests, psutil)
echo "[2/5] Checking apps & Python dependencies..."
if ! python3 -c "import PyQt5" > /dev/null 2>&1; then
    echo "[*] Installing PyQt5 for Apple Dynamic Island Glass HUD..."
    if command -v apt-get > /dev/null 2>&1; then
        sudo apt-get update -y > /dev/null 2>&1 && sudo apt-get install -y python3-pyqt5 python3-pip python3-requests python3-psutil > /dev/null 2>&1 || true
    fi
    if ! python3 -c "import PyQt5" > /dev/null 2>&1; then
        PIP_FLAGS="--quiet"
        if pip3 install --help 2>&1 | grep -q "break-system-packages"; then
            PIP_FLAGS="--quiet --break-system-packages"
        fi
        pip3 install $PIP_FLAGS PyQt5 requests psutil 2>/dev/null || pip install $PIP_FLAGS PyQt5 requests psutil 2>/dev/null || true
    fi
fi

# 3. Check & Install Ollama and verify local model
echo "[3/5] Verifying Ollama and local model (${MODEL_NAME})..."
if ! command -v ollama > /dev/null 2>&1; then
    echo "[*] Ollama not found. Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh 2>/dev/null || true
fi

# Ensure Ollama service is running
if ! pgrep -f "ollama serve" > /dev/null 2>&1; then
    echo "[*] Starting Ollama service..."
    if command -v systemctl > /dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q "ollama.service"; then
        sudo systemctl start ollama 2>/dev/null || systemctl start ollama 2>/dev/null || nohup ollama serve > /dev/null 2>&1 &
    else
        nohup ollama serve > /dev/null 2>&1 &
    fi
    sleep 2
fi

# Check and pull model in background so agent HUD launches immediately without blocking
if command -v ollama > /dev/null 2>&1; then
    BASE_MODEL=$(echo "${MODEL_NAME}" | cut -d: -f1)
    if ! ollama list 2>/dev/null | grep -qi "${BASE_MODEL}"; then
        echo "[*] Model '${MODEL_NAME}' downloading in background so HUD launches immediately..."
        nohup ollama pull "${MODEL_NAME}" > "$AEGIS_DIR/model_pull.log" 2>&1 &
    else
        echo "[✓] Model '${MODEL_NAME}' is ready on local GPU."
    fi
fi

# 4. Download latest standalone agent
echo "[4/5] Downloading latest dgx_agent.py..."
TS=$(date +%s)
DOWNLOADED=false

if curl -fsSL -H "Cache-Control: no-cache" -H "Pragma: no-cache" --connect-timeout 8 "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/dgx_agent.py?v=${TS}" -o "$AGENT_FILE" 2>/dev/null; then
    DOWNLOADED=true
elif curl -k -fsSL -H "Cache-Control: no-cache" -H "Pragma: no-cache" --connect-timeout 6 "${STORAGE_URL}/dgx_agent.py?v=${TS}" -o "$AGENT_FILE" 2>/dev/null; then
    DOWNLOADED=true
fi

if [ "$DOWNLOADED" = false ] || [ ! -s "$AGENT_FILE" ]; then
    if [ -s "$HOME/dgx_agent.py" ]; then
        cp "$HOME/dgx_agent.py" "$AGENT_FILE"
        echo "[✓] Using backup ~/dgx_agent.py"
    else
        echo "[✗] ERROR: Could not download dgx_agent.py! Check internet/Tailscale."
        exit 1
    fi
fi
chmod +x "$AGENT_FILE"
echo "[✓] Agent saved ($(wc -l < "$AGENT_FILE") lines) -> $AGENT_FILE"

# 5. Display & Authorization setup (Respect active user desktop display)
ACTIVE_DISP=""
# If DISPLAY is already set and not an SSH forwarding display (e.g. localhost:10.0), use it directly!
if [ -n "$DISPLAY" ] && [[ "$DISPLAY" != localhost* ]] && [[ "$DISPLAY" != 127.0.0.1* ]]; then
    ACTIVE_DISP="$DISPLAY"
fi

if [ -z "$ACTIVE_DISP" ]; then
    # Discover active user desktop display from who or w
    USER_DISP=$(who 2>/dev/null | grep -o '(:[0-9]*)' | head -1 | tr -d '()')
    if [ -n "$USER_DISP" ]; then
        ACTIVE_DISP="$USER_DISP"
    fi
fi

if [ -z "$ACTIVE_DISP" ]; then
    # Fallback: Check sockets (user session is usually :1 or :0 on modern Ubuntu)
    for d in 1 0 2; do
        if [ -e "/tmp/.X11-unix/X${d}" ]; then
            ACTIVE_DISP=":${d}"
            break
        fi
    done
fi
ACTIVE_DISP="${ACTIVE_DISP:-:0}"

if [ -z "$XAUTHORITY" ] || [ ! -f "$XAUTHORITY" ]; then
    for xa in "$HOME/.Xauthority" "/run/user/$(id -u)/gdm/Xauthority" "/run/user/$(id -u)/gdm3/Xauthority" /run/user/$(id -u)/.mutter-Xwaylandauth* /run/user/$(id -u)/xauth_*; do
        if [ -f "$xa" ]; then
            export XAUTHORITY="$xa"
            break
        fi
    done
fi
xhost +local: > /dev/null 2>&1 || true
xhost + > /dev/null 2>&1 || true

# Generate Start, Stop, and Status scripts
cat <<EOF > "$AEGIS_DIR/start.sh"
#!/usr/bin/env bash
pkill -9 -f "dgx_agent" > /dev/null 2>&1 || true
sleep 0.5
if ! pgrep -f "ollama serve" > /dev/null 2>&1; then
    nohup ollama serve > /dev/null 2>&1 &
    sleep 2
fi
export QT_XCB_GL_INTEGRATION=none
unset WINDOWID
unset GNOME_TERMINAL_SCREEN
unset GNOME_TERMINAL_SERVICE
export DISPLAY="${ACTIVE_DISP}"
for xa in "\$HOME/.Xauthority" "/run/user/\$(id -u)/gdm/Xauthority" "/run/user/\$(id -u)/gdm3/Xauthority" /run/user/\$(id -u)/.mutter-Xwaylandauth* /run/user/\$(id -u)/xauth_*; do
    if [ -f "\$xa" ]; then
        export XAUTHORITY="\$xa"
        break
    fi
done
xhost +local: > /dev/null 2>&1 || true
xhost + > /dev/null 2>&1 || true
pkill -9 -f "dgx_agent" > /dev/null 2>&1 || true
sleep 1
cd "${AEGIS_DIR}"
nohup python3 "${AGENT_FILE}" \
    --id "${NODE_ID}" \
    --gateway "${GATEWAY_URL}" \
    --storage "${STORAGE_URL}" \
    --model "${MODEL_NAME}" \
    --ctx 65536 \
    >> "${LOG_FILE}" 2>&1 &
disown
echo "● Started ${NODE_ID} in background."
EOF
chmod +x "$AEGIS_DIR/start.sh"

cat <<EOF > "$AEGIS_DIR/stop.sh"
#!/usr/bin/env bash
pkill -9 -f "dgx_agent" > /dev/null 2>&1 || true
echo "○ Stopped ${NODE_ID}."
EOF
chmod +x "$AEGIS_DIR/stop.sh"

cat <<EOF > "$AEGIS_DIR/status.sh"
#!/usr/bin/env bash
echo "═══ AEGIS ${NODE_ID} Status ═══"
if pgrep -f "dgx_agent" > /dev/null 2>&1; then
    PID=\$(pgrep -f "dgx_agent" | head -1)
    echo "● RUNNING (PID: \$PID)"
else
    echo "○ NOT RUNNING"
fi
echo ""
echo "Last 8 logs:"
tail -n 8 "${LOG_FILE}" 2>/dev/null || echo "(no logs yet)"
EOF
chmod +x "$AEGIS_DIR/status.sh"

# Symlinks in $HOME
ln -sf "$AEGIS_DIR/start.sh"  "$HOME/start_${NODE_ID}.sh"
ln -sf "$AEGIS_DIR/stop.sh"   "$HOME/stop_${NODE_ID}.sh"
ln -sf "$AEGIS_DIR/status.sh" "$HOME/status_${NODE_ID}.sh"

# Launch agent NOW
echo "[5/5] Launching AEGIS ${NODE_ID}..."
"$AEGIS_DIR/start.sh"
sleep 2

if pgrep -f "dgx_agent" > /dev/null 2>&1; then
    PID=$(pgrep -f "dgx_agent" | head -1)
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║  ✅ SUCCESS! AEGIS ${NODE_ID} (${ROLE}) is now RUNNING!         "
    echo "╠══════════════════════════════════════════════════════════════════╣"
    echo "║  PID:        ${PID}                                             "
    echo "║  Display:    ${ACTIVE_DISP} (Apple Dynamic Island Top-Center)   "
    echo "║  Log File:   ${LOG_FILE}                                        "
    echo "║  Model:      ${MODEL_NAME}                                       "
    echo "║                                                                  "
    echo "║  👉 Dynamic Island notch monitor par top-center par dikhega!    "
    echo "║  👉 Live log dekhne ke liye: tail -f ${LOG_FILE}                 "
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
else
    echo "[!] Process failed to start. Last logs from ${LOG_FILE}:"
    tail -n 20 "${LOG_FILE}" 2>/dev/null || true
fi
