#!/usr/bin/env bash
# ==============================================================================
# AEGIS Universal DGX Node Setup & Update Script (Bulletproof - Zero Sudo)
# ==============================================================================
# SAME PERMANENT COMMAND FOR EVERY NODE:
#   Node 1: curl -fsSL https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_server/dgx_setup.sh | bash
#   Node 2: curl -fsSL https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_server/dgx_setup2.sh | bash
#   Node 3: curl -fsSL https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_server/dgx_setup3.sh | bash
# ==============================================================================

NODE_ID="${1:-dgx-node-5}"
STORAGE_URL="${2:-https://labg418pc12.tailc8c1f6.ts.net:8443}"
GATEWAY_URL="${3:-https://labg418pc12.tailc8c1f6.ts.net}"

# Extract number
NODE_NUM=$(echo "$NODE_ID" | grep -oP '\d+$' || echo "1")

# Default model
MODEL_NAME="qwen2.5-coder:32b"
ROLE="Worker"
case "$NODE_ID" in
    "dgx-node-1") ROLE="Lead Coder" ;;
    "dgx-node-2") ROLE="Reviewer & QA" ;;
    "dgx-node-3") ROLE="Multimodal Vision" ;;
    "dgx-node-4") ROLE="Writer & Reasoner" ;;
    "dgx-node-5") ROLE="Security Auditor" ;;
    "dgx-node-6") ROLE="Visual Studio" ;;
    "dgx-node-7") ROLE="Tool & Git Agent" ;;
    "dgx-node-8") ROLE="Doc Synthesizer" ;;
esac

AEGIS_HOME="$HOME/aegis/${NODE_ID}"
AGENT_FILE="$AEGIS_HOME/dgx_agent.py"
LOG_FILE="$AEGIS_HOME/agent.log"

mkdir -p "$AEGIS_HOME"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  🚀 AEGIS Setup & Launch — ${NODE_ID} (${ROLE})                 "
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  📁 Folder:  ${AEGIS_HOME}"
echo "║  🌐 Gateway: ${GATEWAY_URL}"
echo "║  💾 Vault:   ${STORAGE_URL}"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Stop any old instance of THIS node
echo "[1/4] Stopping old agent (if running)..."
pkill -9 -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
sleep 1

# 2. Download latest agent from local PC Vault or GitHub
echo "[2/4] Downloading latest dgx_agent.py..."
DOWNLOAD_SUCCESS=false
if curl -fsSL --connect-timeout 4 "${STORAGE_URL}/dgx_agent.py" -o "$AGENT_FILE" 2>/dev/null; then
    DOWNLOAD_SUCCESS=true
elif curl -fsSL --connect-timeout 8 "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/dgx_agent.py" -o "$AGENT_FILE" 2>/dev/null; then
    DOWNLOAD_SUCCESS=true
fi

if [ "$DOWNLOAD_SUCCESS" = false ] || [ ! -s "$AGENT_FILE" ]; then
    echo "[!] Download failed from both PC Vault and GitHub. Checking local backup..."
    if [ -s "$HOME/dgx_agent.py" ]; then
        cp "$HOME/dgx_agent.py" "$AGENT_FILE"
        echo "[✓] Using backup ~/dgx_agent.py"
    else
        echo "[✗] ERROR: Could not fetch dgx_agent.py! Check internet/Tailscale."
        exit 1
    fi
fi
chmod +x "$AGENT_FILE"
cp "$AGENT_FILE" "$HOME/dgx_agent.py" 2>/dev/null || true
echo "[✓] Agent saved → $AGENT_FILE ($(wc -l < "$AGENT_FILE") lines)"

# 3. Detect Python runtime
echo "[3/4] Checking Python environment..."
PY_BIN="python3"
if ! command -v python3 &> /dev/null; then
    if command -v python &> /dev/null; then
        PY_BIN="python"
    else
        echo "[✗] ERROR: python3 not found! Please install python3."
        exit 1
    fi
fi

# Detect display
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
export DISPLAY="$ACTIVE_DISP"

# X11 authorization
if [ -z "${XAUTHORITY:-}" ]; then
    for xa in "$HOME/.Xauthority" "/run/user/$(id -u)/gdm/Xauthority" "/run/user/$(id -u)/gdm3/Xauthority"; do
        if [ -f "$xa" ]; then
            export XAUTHORITY="$xa"
            break
        fi
    done
fi
xhost +local: > /dev/null 2>&1 || true

# 4. Generate standalone launcher & stop scripts
cat <<EOF > "$AEGIS_HOME/start.sh"
#!/usr/bin/env bash
pkill -9 -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
sleep 0.5
export DISPLAY="${ACTIVE_DISP}"
[ -f "$HOME/.Xauthority" ] && export XAUTHORITY="$HOME/.Xauthority"
xhost +local: > /dev/null 2>&1 || true
nohup ${PY_BIN} "${AGENT_FILE}" \
    --id "${NODE_ID}" \
    --gateway "${GATEWAY_URL}" \
    --storage "${STORAGE_URL}" \
    --model "${MODEL_NAME}" \
    --ctx 65536 \
    >> "${LOG_FILE}" 2>&1 &
disown
EOF
chmod +x "$AEGIS_HOME/start.sh"

cat <<EOF > "$AEGIS_HOME/stop.sh"
#!/usr/bin/env bash
pkill -9 -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
echo "[✓] AEGIS ${NODE_ID} stopped."
EOF
chmod +x "$AEGIS_HOME/stop.sh"

cat <<EOF > "$AEGIS_HOME/status.sh"
#!/usr/bin/env bash
echo "═══ AEGIS ${NODE_ID} Status ═══"
if pgrep -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1; then
    PID=\$(pgrep -f "dgx_agent.py --id ${NODE_ID}" | head -1)
    echo "● RUNNING (PID: \$PID)"
else
    echo "○ NOT RUNNING"
fi
echo ""
echo "Last 10 logs:"
tail -n 10 "${LOG_FILE}" 2>/dev/null || echo "(no logs yet)"
EOF
chmod +x "$AEGIS_HOME/status.sh"

# Convenience symlinks in $HOME
ln -sf "$AEGIS_HOME/start.sh"  "$HOME/start_aegis_${NODE_NUM}.sh"
ln -sf "$AEGIS_HOME/stop.sh"   "$HOME/stop_aegis_${NODE_NUM}.sh"
ln -sf "$AEGIS_HOME/status.sh" "$HOME/status_aegis_${NODE_NUM}.sh"

# 5. Launch NOW in background with nohup + disown
echo "[4/4] Starting agent in background..."
"$AEGIS_HOME/start.sh"
sleep 1.5

if pgrep -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1; then
    PID=$(pgrep -f "dgx_agent.py --id ${NODE_ID}" | head -1)
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║  ✅ SUCCESS! AEGIS ${NODE_ID} is now RUNNING!                    "
    echo "╠══════════════════════════════════════════════════════════════════╣"
    echo "║  Process PID:   ${PID}"
    echo "║  Display:       ${ACTIVE_DISP} (Apple-style Pastel Dynamic Island)"
    echo "║  Log File:      ${LOG_FILE}"
    echo "║"
    echo "║  👉 Aap terminal BAND kar sakte ho — agent background me chalega!"
    echo "║  👉 Log dekhna ho to: tail -f ${LOG_FILE}"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
else
    echo ""
    echo "[!] Process start hua par exit ho gaya. Checking log:"
    tail -n 15 "$LOG_FILE" 2>/dev/null || echo "(no logs)"
    echo ""
    echo "Manually run karke error dekhne ke liye: ${PY_BIN} ${AGENT_FILE} --id ${NODE_ID}"
fi
