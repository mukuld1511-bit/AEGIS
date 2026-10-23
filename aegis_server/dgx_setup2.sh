#!/usr/bin/env bash
# ==============================================================================
# AEGIS Standalone DGX Node 2 Setup & Launcher (From Scratch)
# Node: dgx-node-2 (Reviewer & QA)
# ==============================================================================
set -e

NODE_ID="dgx-node-2"
ROLE="Reviewer & QA"
GATEWAY_URL="https://labg418pc12.tailc8c1f6.ts.net"
STORAGE_URL="https://labg418pc12.tailc8c1f6.ts.net:8443"
MODEL_NAME="qwen2.5-coder:32b"

AEGIS_HOME="$HOME/aegis/${NODE_ID}"
AGENT_FILE="$AEGIS_HOME/dgx_agent.py"
LOG_FILE="$AEGIS_HOME/agent.log"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  🚀 AEGIS DGX Node 2 Setup & Launcher (${ROLE})                 "
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Node ID:   ${NODE_ID}                                         "
echo "║  Directory: ${AEGIS_HOME}                                       "
echo "║  Gateway:   ${GATEWAY_URL}                                      "
echo "║  Vault:     ${STORAGE_URL}                                      "
echo "║  Model:     ${MODEL_NAME}                                       "
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Stop any old agent instance for Node 2 & clean old Node 1 traces if mistakenly on this machine
echo "[1/4] Stopping any existing Node 2 agent and removing stale Node 1 traces..."
pkill -9 -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
rm -rf "$HOME/aegis/dgx-node-1" "$HOME/start_dgx-node-1.sh" "$HOME/stop_dgx-node-1.sh" "$HOME/status_dgx-node-1.sh" 2>/dev/null || true
rm -rf "$HOME/start_aegis_1.sh" "$HOME/stop_aegis_1.sh" "$HOME/status_aegis_1.sh" 2>/dev/null || true
sleep 1

# 2. Prepare directories
mkdir -p "$AEGIS_HOME/workspace"

# 3. Download fresh standalone agent
echo "[2/4] Downloading latest dgx_agent.py..."
TS=$(date +%s)
DOWNLOADED=false

if curl -fsSL -H "Cache-Control: no-cache" -H "Pragma: no-cache" --connect-timeout 6 "${STORAGE_URL}/dgx_agent.py?v=${TS}" -o "$AGENT_FILE" 2>/dev/null; then
    DOWNLOADED=true
elif curl -fsSL -H "Cache-Control: no-cache" -H "Pragma: no-cache" --connect-timeout 8 "https://raw.githubusercontent.com/mukuld1511-bit/AEGIS/main/aegis_node/dgx_agent.py?v=${TS}" -o "$AGENT_FILE" 2>/dev/null; then
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

# 4. Display & Authorization setup
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

if [ -z "${XAUTHORITY:-}" ]; then
    for xa in "$HOME/.Xauthority" "/run/user/$(id -u)/gdm/Xauthority" "/run/user/$(id -u)/gdm3/Xauthority"; do
        if [ -f "$xa" ]; then
            export XAUTHORITY="$xa"
            break
        fi
    done
fi
xhost +local: > /dev/null 2>&1 || true

# 5. Generate Start, Stop, and Status scripts
cat <<EOF > "$AEGIS_HOME/start.sh"
#!/usr/bin/env bash
pkill -9 -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
sleep 0.5
unset WINDOWID
unset GNOME_TERMINAL_SCREEN
unset GNOME_TERMINAL_SERVICE
export DISPLAY="${ACTIVE_DISP}"
[ -f "$HOME/.Xauthority" ] && export XAUTHORITY="$HOME/.Xauthority"
xhost +local: > /dev/null 2>&1 || true
cd "${AEGIS_HOME}"
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
chmod +x "$AEGIS_HOME/start.sh"

cat <<EOF > "$AEGIS_HOME/stop.sh"
#!/usr/bin/env bash
pkill -9 -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1 || true
echo "○ Stopped ${NODE_ID}."
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

# Symlinks in $HOME
ln -sf "$AEGIS_HOME/start.sh"  "$HOME/start_${NODE_ID}.sh"
ln -sf "$AEGIS_HOME/stop.sh"   "$HOME/stop_${NODE_ID}.sh"
ln -sf "$AEGIS_HOME/status.sh" "$HOME/status_${NODE_ID}.sh"

# 6. Launch agent NOW
echo "[3/4] Launching AEGIS ${NODE_ID}..."
"$AEGIS_HOME/start.sh"
sleep 1.5

if pgrep -f "dgx_agent.py --id ${NODE_ID}" > /dev/null 2>&1; then
    PID=$(pgrep -f "dgx_agent.py --id ${NODE_ID}" | head -1)
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║  ✅ SUCCESS! AEGIS ${NODE_ID} (${ROLE}) is now RUNNING!         "
    echo "╠══════════════════════════════════════════════════════════════════╣"
    echo "║  PID:        ${PID}                                             "
    echo "║  Display:    ${ACTIVE_DISP} (Apple Dynamic Island Top-Center)   "
    echo "║  Log File:   ${LOG_FILE}                                        "
    echo "║                                                                  "
    echo "║  👉 Terminal band kar sakte ho — background me chalega!         "
    echo "║  👉 Live log dekhne ke liye: tail -f ${LOG_FILE}                 "
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
else
    echo "[!] Process started, check log for output: cat ${LOG_FILE}"
fi
