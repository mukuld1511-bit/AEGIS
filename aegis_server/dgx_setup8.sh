#!/usr/bin/env bash
# ==============================================================================
# AEGIS Universal DGX Node Auto-Setup & Update Script (v3 - Bulletproof)
# ==========================================================================
# SAME COMMAND FOR EVERY NODE - just change the number:
#
#   curl -fsSL http://100.88.197.6:9080/setup/1 | bash
#   curl -fsSL http://100.88.197.6:9080/setup/2 | bash
#   curl -fsSL http://100.88.197.6:9080/setup/3 | bash
#   curl -fsSL http://100.88.197.6:9080/setup/4 | bash
#   curl -fsSL http://100.88.197.6:9080/setup/5 | bash
#   curl -fsSL http://100.88.197.6:9080/setup/6 | bash
#   curl -fsSL http://100.88.197.6:9080/setup/7 | bash
#   curl -fsSL http://100.88.197.6:9080/setup/8 | bash
#
# OR with explicit node ID argument:
#   curl -fsSL http://100.88.197.6:9080/setup | bash -s -- dgx-node-1
#
# RE-RUN ANYTIME TO UPDATE:
#   Same command har baar chalao - purana kill, naya download, restart!
# ==============================================================================
set -e

# ── 1. Parse Node ID ─────────────────────────────────────────────────
NODE_ID="${1:-dgx-node-8}"
STORAGE_URL="${2:-http://100.88.197.6:9080}"
GATEWAY_URL="${3:-http://100.88.197.6:9000}"

# Extract node number from ID (dgx-node-3 -> 3)
NODE_NUM=$(echo "$NODE_ID" | grep -oP '\d+$' || echo "1")

# ── 2. Auto-Assign Model Per Node Role ───────────────────────────────
if [ -z "$4" ]; then
    case "$NODE_ID" in
        "dgx-node-1") MODEL_NAME="qwen2.5-coder:32b"             ; ROLE="Lead Coder" ;;
        "dgx-node-2") MODEL_NAME="qwen2.5-coder:32b"             ; ROLE="Reviewer & QA" ;;
        "dgx-node-3") MODEL_NAME="pixtral-large:124b-q4_K_M"     ; ROLE="Multimodal Vision" ;;
        "dgx-node-4") MODEL_NAME="mixtral:8x22b-instruct-q4_K_M" ; ROLE="Writer & Deep Reasoner" ;;
        "dgx-node-5") MODEL_NAME="mixtral:8x22b-instruct-q4_K_M" ; ROLE="Security Auditor" ;;
        "dgx-node-6") MODEL_NAME="qwen2.5-coder:32b"             ; ROLE="Generative Visual Studio" ;;
        "dgx-node-7") MODEL_NAME="qwen2.5-coder:32b"             ; ROLE="Tool & Git Agent" ;;
        "dgx-node-8") MODEL_NAME="mixtral:8x22b-instruct-q4_K_M" ; ROLE="Document Synthesizer" ;;
        *)            MODEL_NAME="qwen2.5-coder:32b"             ; ROLE="Generic Worker" ;;
    esac
else
    MODEL_NAME="$4"
    ROLE="Custom"
fi

# ── 3. Dedicated Node Directory ──────────────────────────────────────
AEGIS_HOME="$HOME/aegis/${NODE_ID}"
AGENT_FILE="$AEGIS_HOME/dgx_agent.py"
LOG_FILE="$AEGIS_HOME/agent.log"

mkdir -p "$AEGIS_HOME"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  🚀 AEGIS Universal Setup — ${NODE_ID} (${ROLE})               "
echo "║  Model:   ${MODEL_NAME}                                        "
echo "║  Folder:  ${AEGIS_HOME}                                        "
echo "║  Vault:   ${STORAGE_URL}                                       "
echo "║  Gateway: ${GATEWAY_URL}                                       "
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ── 4. Kill any previously running agent for THIS node ────────────────
echo "[1/6] Stopping old agent for ${NODE_ID} (if running)..."
pkill -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
sleep 1

# ── 5. Download Latest Agent (Always fresh from PC Vault or GitHub) ──
echo "[2/6] Downloading latest dgx_agent.py..."
curl -fsSL "${STORAGE_URL}/dgx_agent.py" -o "$AGENT_FILE" 2>/dev/null || \
curl -fsSL "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/dgx_agent.py" -o "$AGENT_FILE" || {
    echo "[✗] FATAL: Could not download dgx_agent.py from Vault or GitHub!"
    exit 1
}
chmod +x "$AGENT_FILE"

# Also keep a copy at ~/dgx_agent.py for backward compat
cp "$AGENT_FILE" "$HOME/dgx_agent.py" 2>/dev/null || true

echo "[✓] Agent saved → $AGENT_FILE ($(wc -l < "$AGENT_FILE") lines)"

# ── 6. Ollama GPU Runtime ────────────────────────────────────────────
echo "[3/6] Verifying Ollama GPU runtime..."
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

# ── 7. Pull Model ───────────────────────────────────────────────────
echo "[4/6] Pulling ${MODEL_NAME} on local GPU (128GB Unified)..."
ollama pull "${MODEL_NAME}" 2>/dev/null || ollama pull "qwen2.5-coder:32b" 2>/dev/null || true
echo "[✓] Model ready: ${MODEL_NAME}"

# ── 8. Install PyQt5 for Dynamic Island HUD ──────────────────────────
echo "[5/6] Ensuring GUI dependencies for Parakeet AI Neon Green HUD..."
sudo apt-get update -y > /dev/null 2>&1 || true
sudo apt-get install -y python3-pyqt5 python3-tk > /dev/null 2>&1 || pip3 install PyQt5 2>/dev/null || true

# ── 9. X11 Display Detection ────────────────────────────────────────
ACTIVE_DISP="${DISPLAY:-}"
if [ -z "$ACTIVE_DISP" ]; then
    for d in 0 1 2; do
        if [ -e "/tmp/.X11-unix/X${d}" ]; then
            ACTIVE_DISP=":${d}"
            break
        fi
    done
    [ -z "$ACTIVE_DISP" ] && ACTIVE_DISP=":0"
fi
xhost +local: > /dev/null 2>&1 || true

# Detect XAUTHORITY
ACTIVE_XAUTH="${XAUTHORITY:-}"
if [ -z "$ACTIVE_XAUTH" ]; then
    for xa in "$HOME/.Xauthority" "/run/user/$(id -u)/gdm/Xauthority" "/run/user/$(id -u)/gdm3/Xauthority"; do
        if [ -f "$xa" ]; then
            ACTIVE_XAUTH="$xa"
            break
        fi
    done
    [ -z "$ACTIVE_XAUTH" ] && ACTIVE_XAUTH="$HOME/.Xauthority"
fi

echo "[✓] Display: ${ACTIVE_DISP}  |  XAuth: ${ACTIVE_XAUTH}"

# ── 10. Create Silent Background Launcher ────────────────────────────
echo "[6/6] Creating launcher scripts..."

cat <<'LAUNCHER_EOF' > "$AEGIS_HOME/start.sh"
#!/usr/bin/env bash
# ── AEGIS Silent Launcher for __NODE_ID__ ──
# Re-run this anytime. Kills old, starts fresh. Terminal band karo freely.

NODE_ID="__NODE_ID__"
AEGIS_HOME="__AEGIS_HOME__"
AGENT_FILE="__AGENT_FILE__"
LOG_FILE="__LOG_FILE__"
GATEWAY_URL="__GATEWAY_URL__"
STORAGE_URL="__STORAGE_URL__"
MODEL_NAME="__MODEL_NAME__"

# Kill previous instance of THIS node only
pkill -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
sleep 0.5

# X11 Display
ACTIVE_DISP="${DISPLAY:-}"
if [ -z "$ACTIVE_DISP" ]; then
    for d in 0 1 2; do
        [ -e "/tmp/.X11-unix/X${d}" ] && ACTIVE_DISP=":${d}" && break
    done
    [ -z "$ACTIVE_DISP" ] && ACTIVE_DISP=":0"
fi
export DISPLAY="$ACTIVE_DISP"

# XAUTHORITY
if [ -z "${XAUTHORITY:-}" ]; then
    for xa in "$HOME/.Xauthority" "/run/user/$(id -u)/gdm/Xauthority"; do
        [ -f "$xa" ] && export XAUTHORITY="$xa" && break
    done
fi
xhost +local: > /dev/null 2>&1 || true

# Launch agent in background with log file
nohup /usr/bin/python3 "$AGENT_FILE" \
    --id "$NODE_ID" \
    --gateway "$GATEWAY_URL" \
    --storage "$STORAGE_URL" \
    --model "$MODEL_NAME" \
    --ctx 65536 \
    >> "$LOG_FILE" 2>&1 &
disown

PID=$!
echo "════════════════════════════════════════════════════════"
echo " [✓] AEGIS ${NODE_ID} launched (PID: $PID)"
echo " [✓] Dynamic Island HUD on DISPLAY $ACTIVE_DISP"
echo " [✓] Log: tail -f $LOG_FILE"
echo " [✓] Terminal BAND kar sakte ho — agent chalega!"
echo "════════════════════════════════════════════════════════"
LAUNCHER_EOF

# Replace placeholders with actual values
sed -i "s|__NODE_ID__|${NODE_ID}|g"       "$AEGIS_HOME/start.sh"
sed -i "s|__AEGIS_HOME__|${AEGIS_HOME}|g" "$AEGIS_HOME/start.sh"
sed -i "s|__AGENT_FILE__|${AGENT_FILE}|g" "$AEGIS_HOME/start.sh"
sed -i "s|__LOG_FILE__|${LOG_FILE}|g"     "$AEGIS_HOME/start.sh"
sed -i "s|__GATEWAY_URL__|${GATEWAY_URL}|g" "$AEGIS_HOME/start.sh"
sed -i "s|__STORAGE_URL__|${STORAGE_URL}|g" "$AEGIS_HOME/start.sh"
sed -i "s|__MODEL_NAME__|${MODEL_NAME}|g"   "$AEGIS_HOME/start.sh"
chmod +x "$AEGIS_HOME/start.sh"

# ── Stop Script ──
cat <<EOF > "$AEGIS_HOME/stop.sh"
#!/usr/bin/env bash
# Stop AEGIS ${NODE_ID} agent & HUD
pkill -9 -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
echo "[✓] AEGIS ${NODE_ID} stopped."
EOF
chmod +x "$AEGIS_HOME/stop.sh"

# ── Status Script ──
cat <<EOF > "$AEGIS_HOME/status.sh"
#!/usr/bin/env bash
# Check AEGIS ${NODE_ID} status
echo "═══════ AEGIS ${NODE_ID} Status ═══════"
if pgrep -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1; then
    PID=\$(pgrep -f "dgx_agent.py --id ${NODE_ID}" | head -1)
    echo "● RUNNING (PID: \$PID)"
else
    echo "○ NOT RUNNING"
fi
echo ""
echo "── Last 10 log lines ──"
tail -10 "${LOG_FILE}" 2>/dev/null || echo "(no log yet)"
echo ""
echo "── Agent File ──"
ls -lh "${AGENT_FILE}" 2>/dev/null || echo "(not found)"
EOF
chmod +x "$AEGIS_HOME/status.sh"

# ── Update Script (re-download and restart) ──
cat <<EOF > "$AEGIS_HOME/update.sh"
#!/usr/bin/env bash
# Update & Restart AEGIS ${NODE_ID} — downloads latest agent, restarts
echo "[*] Updating ${NODE_ID}..."
pkill -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
sleep 1
curl -fsSL "${STORAGE_URL}/dgx_agent.py" -o "${AGENT_FILE}" 2>/dev/null || \\
curl -fsSL "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/dgx_agent.py" -o "${AGENT_FILE}"
chmod +x "${AGENT_FILE}"
echo "[✓] Agent updated (\$(wc -l < "${AGENT_FILE}") lines)"
"${AEGIS_HOME}/start.sh"
EOF
chmod +x "$AEGIS_HOME/update.sh"

# ── Symlinks in $HOME for convenience ──
ln -sf "$AEGIS_HOME/start.sh"  "$HOME/start_aegis_${NODE_NUM}.sh"
ln -sf "$AEGIS_HOME/stop.sh"   "$HOME/stop_aegis_${NODE_NUM}.sh"
ln -sf "$AEGIS_HOME/status.sh" "$HOME/status_aegis_${NODE_NUM}.sh"
ln -sf "$AEGIS_HOME/update.sh" "$HOME/update_aegis_${NODE_NUM}.sh"

# Also keep legacy symlinks for node 1
if [ "$NODE_NUM" = "1" ]; then
    ln -sf "$AEGIS_HOME/start.sh"  "$HOME/start_aegis_silent.sh"
    ln -sf "$AEGIS_HOME/stop.sh"   "$HOME/stop_aegis.sh"
fi

# ── 11. XDG Desktop Autostart (DGX boots → agent auto-starts silently) ──
mkdir -p "$HOME/.config/autostart"
cat <<EOF > "$HOME/.config/autostart/aegis-${NODE_ID}.desktop"
[Desktop Entry]
Type=Application
Name=AEGIS ${NODE_ID} (${ROLE})
Comment=Parakeet AI Neon Green Dynamic Island & Floating Corner HUD
Exec=${AEGIS_HOME}/start.sh
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
Categories=Utility;Development;
EOF
chmod +x "$HOME/.config/autostart/aegis-${NODE_ID}.desktop"

# ── 12. Desktop Shortcuts ──
mkdir -p "$HOME/Desktop"
cat <<EOF > "$HOME/Desktop/AEGIS-${NODE_ID}-Start.desktop"
[Desktop Entry]
Type=Application
Name=▶ AEGIS ${NODE_ID} Start
Exec=${AEGIS_HOME}/start.sh
Terminal=false
Icon=utilities-system-monitor
EOF
chmod +x "$HOME/Desktop/AEGIS-${NODE_ID}-Start.desktop"

cat <<EOF > "$HOME/Desktop/AEGIS-${NODE_ID}-Stop.desktop"
[Desktop Entry]
Type=Application
Name=■ AEGIS ${NODE_ID} Stop
Exec=${AEGIS_HOME}/stop.sh
Terminal=false
Icon=process-stop
EOF
chmod +x "$HOME/Desktop/AEGIS-${NODE_ID}-Stop.desktop"

# ── 13. systemd Service (survives reboot without login) ──
SERVICE_NAME="aegis-${NODE_ID}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo bash -c "cat <<SVCEOF > ${SERVICE_FILE}
[Unit]
Description=AEGIS Autonomous DGX Agent (${NODE_ID} - ${ROLE})
After=network.target graphical.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${AEGIS_HOME}
Environment=DISPLAY=${ACTIVE_DISP}
Environment=XAUTHORITY=${ACTIVE_XAUTH}
ExecStart=/usr/bin/python3 ${AGENT_FILE} --id ${NODE_ID} --gateway ${GATEWAY_URL} --storage ${STORAGE_URL} --model ${MODEL_NAME} --ctx 65536
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=graphical.target
SVCEOF"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service" > /dev/null 2>&1 || true
loginctl enable-linger "${USER}" > /dev/null 2>&1 || true

# ── 14. Launch NOW ──
"$AEGIS_HOME/start.sh"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  ✅ AEGIS ${NODE_ID} (${ROLE}) — SETUP COMPLETE!               "
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║                                                                 "
echo "║  📁 Node Folder:  ${AEGIS_HOME}                                "
echo "║  📜 Agent File:   ${AGENT_FILE}                                "
echo "║  📋 Live Log:     tail -f ${LOG_FILE}                          "
echo "║                                                                 "
echo "║  🔧 Helper Scripts (from anywhere):                            "
echo "║      ~/start_aegis_${NODE_NUM}.sh   → Start/Restart            "
echo "║      ~/stop_aegis_${NODE_NUM}.sh    → Stop                     "
echo "║      ~/status_aegis_${NODE_NUM}.sh  → Check status & logs      "
echo "║      ~/update_aegis_${NODE_NUM}.sh  → Download latest & restart"
echo "║                                                                 "
echo "║  🔄 UPDATE KARNA HO TO:                                        "
echo "║      curl -fsSL ${STORAGE_URL}/setup/${NODE_NUM} | bash         "
echo "║      (same command — kill → download → restart automatic!)      "
echo "║                                                                 "
echo "║  🖥  DGX BOOT: Auto-starts silently (systemd + XDG autostart)  "
echo "║  🎯 Model: ${MODEL_NAME}                                       "
echo "║  🌐 Gateway: ${GATEWAY_URL} (6s heartbeat polling)             "
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
