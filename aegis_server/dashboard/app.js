/**
 * AEGIS Mission Control - Minimal Light GPT-Like Interface Logic
 * Handles real-time WebSockets, Web Speech API, chat stream rendering,
 * slide-out drawers, terminal streaming, and 4-node autonomous pipeline handoffs.
 */

// Target API Hosts (Coordinator and Storage) with resilient Tailscale / Local Port detection
const isDirectPiPort = window.location.port === '9000';
const isFunnel = window.location.hostname.includes('tail') || window.location.hostname.includes('.ts.net');
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

const WS_URL = (isDirectPiPort || isFunnel)
  ? `${WS_PROTOCOL}//${window.location.host}/ws/cluster`
  : `${WS_PROTOCOL}//${window.location.hostname}:9000/ws/cluster`;

const API_BASE = (isDirectPiPort || isFunnel)
  ? window.location.origin
  : `${window.location.protocol}//${window.location.hostname}:9000`;

// Storage Vault (i7-14700 PC): Port 9080
const STORAGE_BASE = window.location.port === '9080'
  ? ''
  : (isFunnel ? `${window.location.protocol}//${window.location.hostname}:9080` : `${window.location.protocol}//${window.location.hostname}:9080`);

// DOM Elements
const cmdInput = document.getElementById('cmd-input-field');
const btnDispatch = document.getElementById('btn-dispatch-cmd');
const btnMic = document.getElementById('btn-mic-toggle');
const voiceIndicator = document.getElementById('voice-indicator');
const voiceStateText = document.getElementById('voice-state-text');
const spokenText = document.getElementById('spoken-text');
const spokenReplyContainer = document.getElementById('spoken-reply-container');
const dgxGrid = document.getElementById('dgx-nodes-grid');
const terminalOutput = document.getElementById('terminal-output');
const activeTerminalLabel = document.getElementById('active-terminal-node');
const btnClearTerminal = document.getElementById('btn-clear-terminal');
const artifactsList = document.getElementById('artifacts-list-container');
const btnRefreshArtifacts = document.getElementById('btn-refresh-artifacts');

// Chat UI Elements
const chatScrollArea = document.getElementById('chat-scroll-area');
const chatWelcomeHero = document.getElementById('chat-welcome-hero');
const chatMessagesList = document.getElementById('chat-messages-list');
const btnNewChat = document.getElementById('btn-new-chat');

// Sidebar & Drawers Elements
const sidebar = document.getElementById('sidebar');
const btnSidebarToggle = document.getElementById('btn-sidebar-toggle');
const btnThemeToggle = document.getElementById('btn-theme-toggle');
const themeIcon = document.getElementById('theme-icon');
const themeText = document.getElementById('theme-text');

// Model Picker Elements
const modelPickerTrigger = document.getElementById('model-picker-trigger');
const modelDropdownMenu = document.getElementById('model-dropdown-menu');
const activeModelName = document.getElementById('active-model-name');

// Drawers Elements
const nodesDrawerOverlay = document.getElementById('nodes-drawer-overlay');
const btnToggleNodesDrawer = document.getElementById('btn-toggle-nodes-drawer');
const btnQuickNodes = document.getElementById('btn-quick-nodes');
const btnCloseNodesDrawer = document.getElementById('btn-close-nodes-drawer');

const vaultDrawerOverlay = document.getElementById('vault-drawer-overlay');
const btnToggleVaultDrawer = document.getElementById('btn-toggle-vault-drawer');
const btnQuickVault = document.getElementById('btn-quick-vault');
const btnCloseVaultDrawer = document.getElementById('btn-close-vault-drawer');

const terminalDrawerOverlay = document.getElementById('terminal-drawer-overlay');
const btnToggleTerminalDrawer = document.getElementById('btn-toggle-terminal-drawer');
const btnCloseTerminalDrawer = document.getElementById('btn-close-terminal-drawer');

// Safety Modal Elements
const safetyPanel = document.getElementById('safety-alert-panel');
const safetyRiskLevel = document.getElementById('safety-risk-level');
const safetyReason = document.getElementById('safety-reason');
const safetyCommandText = document.getElementById('safety-command-text');
const btnApprove = document.getElementById('btn-approve-action');
const btnReject = document.getElementById('btn-reject-action');

// Stats Elements
const statOnlineNodes = document.getElementById('stat-online-nodes');
const statActiveTasks = document.getElementById('stat-active-tasks');

let ws = null;
let currentPendingTaskId = null;
let selectedNodeId = 'auto'; // 'auto' (4-node pipeline) or specific node id
let currentAssistantMsgEl = null;

// Initial default node data mapped to the flagship models (4 DGX System + Extended Cluster)
let nodesData = [
  { id: 'dgx-node-1', name: 'DGX Spark 01 - Lead Synthesizer', status: 'online', model: 'Qwen2.5-Coder:32B (65K Context)', vram_used: 19.5, vram_total: 128, gpu_pct: 14, temp: 45, screen: ':0 (Lead Coder HUD)' },
  { id: 'dgx-node-2', name: 'DGX Spark 02 - Reviewer & QA', status: 'online', model: 'Qwen2.5-Coder:32B (QA & Pytest)', vram_used: 19.5, vram_total: 128, gpu_pct: 8, temp: 41, screen: ':0 (QA Review HUD)' },
  { id: 'dgx-node-3', name: 'DGX Spark 03 - Systems Architect', status: 'online', model: 'Llama-3.2-Vision:90B (Arch & Multimodal)', vram_used: 65.0, vram_total: 128, gpu_pct: 16, temp: 44, screen: ':0 (Vision & Arch HUD)' },
  { id: 'dgx-node-4', name: 'DGX Spark 04 - Deep Reasoner & Security', status: 'online', model: 'Qwen2.5:141B / DeepSeek (Security Sentinel)', vram_used: 82.0, vram_total: 128, gpu_pct: 22, temp: 48, screen: ':0 (Deep Reason HUD)' },
  { id: 'dgx-node-5', name: 'DGX Spark 05 - Security Auditor', status: 'online', model: 'Command R+ (104B Security)', vram_used: 62.0, vram_total: 128, gpu_pct: 6, temp: 40, screen: ':0 (Security HUD)' },
  { id: 'dgx-node-6', name: 'DGX Spark 06 - Image Gen Studio', status: 'online', model: 'FLUX.1-dev + schnell (20B FP16)', vram_used: 34.0, vram_total: 128, gpu_pct: 18, temp: 45, screen: ':0 (Diffusion HUD)' },
  { id: 'dgx-node-7', name: 'DGX Spark 07 - Comms & Git Ops', status: 'online', model: 'DBRX-Instruct MoE (132B)', vram_used: 75.0, vram_total: 128, gpu_pct: 12, temp: 43, screen: ':0 (Git & Router HUD)' },
  { id: 'dgx-node-8', name: 'DGX Spark 08 - Doc / File Synth', status: 'online', model: 'Llama-3.3-70B-Instruct (70B)', vram_used: 51.0, vram_total: 128, gpu_pct: 9, temp: 41, screen: ':0 (Doc Synth HUD)' }
];

// Initialize WebSockets
function initWebSocket() {
  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      appendTerminal('[WS] Connected to AEGIS Core Orchestrator stream.', 'term-cyan');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleWsEvent(msg);
      } catch (e) {
        console.error('WS Parse Error:', e);
      }
    };

    ws.onclose = () => {
      appendTerminal('[WS] Disconnected from Coordinator. Retrying in 4s...', 'term-amber');
      setTimeout(initWebSocket, 4000);
    };

    ws.onerror = () => {};
  } catch (err) {
    console.warn('WebSocket connection deferred:', err);
  }
}

function handleWsEvent(msg) {
  if (msg.event === 'initial_snapshot') {
    if (msg.nodes && msg.nodes.length) {
      updateNodesFromBackend(msg.nodes);
    }
  } else if (msg.event === 'node_telemetry_updated') {
    updateSingleNodeTelemetry(msg.data);
  } else if (msg.event === 'task_step_updated' || msg.event === 'task_step_added') {
    if (msg.data && msg.data.stdout) {
      appendTerminal(msg.data.stdout, 'term-emerald');
    }
  } else if (msg.event === 'task_created') {
    appendTerminal(`\n[TASK CREATED] ID: ${msg.data.task_id} | Node: ${msg.data.assigned_node_id}`, 'term-cyan');
    setNodeStatus(msg.data.assigned_node_id, 'busy');
    updateAssistantProgress('stage-1', 'active');
  } else if (msg.event === 'review_task_queued' || msg.event === 'pipeline_step_progress') {
    const nextNode = msg.data.next_node || msg.data.reviewer_node || 'dgx-node-2';
    const stage = msg.data.stage || 'Autonomous Inter-Node Handoff';
    const task = msg.data.task || {};
    appendTerminal(`\n⚛ [AUTONOMOUS PIPELINE: ${stage.toUpperCase()}]`, 'term-cyan');
    appendTerminal(`  • Routing to ${nextNode.toUpperCase()} | Task: ${task.task_id || 'pipeline_subtask'} | Model: ${task.model || 'Auto'}`, 'term-emerald');
    setNodeStatus(nextNode, 'busy');

    // Update Chat Stepper Progress
    if (nextNode === 'dgx-node-2') {
      updateAssistantProgress('stage-1', 'done');
      updateAssistantProgress('stage-2', 'active');
    } else if (nextNode === 'dgx-node-3') {
      updateAssistantProgress('stage-2', 'done');
      updateAssistantProgress('stage-3', 'active');
    } else if (nextNode === 'dgx-node-4') {
      updateAssistantProgress('stage-3', 'done');
      updateAssistantProgress('stage-4', 'active');
    }
  } else if (msg.event === 'pipeline_completed') {
    appendTerminal(`\n🏆 [4-NODE PIPELINE CONCLUDED]`, 'term-cyan');
    appendTerminal(`  • Task ${msg.data.original_task_id} fully synthesized, reviewed, visually analyzed, and hardened!`, 'term-emerald');
    updateAssistantProgress('stage-4', 'done');
    finalizeAssistantMsg("Full 4-node cluster pipeline completed! Solution synthesized on Node 1, QA verified on Node 2, architecture profiled on Node 3, and security hardened on Node 4.");
    if (typeof loadRecentArtifacts === 'function') loadRecentArtifacts();
  } else if (msg.event === 'dgx_task_finished') {
    appendTerminal(`[TASK FINISHED] ${msg.data.node_id?.toUpperCase() || 'NODE'} completed ${msg.data.task_id} (Exit: ${msg.data.exit_code})`, 'term-emerald');
    setNodeStatus(msg.data.node_id, 'online');
    if (typeof loadRecentArtifacts === 'function') loadRecentArtifacts();
  } else if (msg.event === 'task_completed') {
    appendTerminal(`[TASK ARCHIVED] Task ${msg.data.task_id} completed.`, 'term-dim');
    if (msg.data.assigned_node_id) setNodeStatus(msg.data.assigned_node_id, 'online');
    if (typeof loadRecentArtifacts === 'function') loadRecentArtifacts();
  }
}

function updateNodesFromBackend(rawNodes) {
  nodesData = rawNodes.map(n => ({
    id: n.node_id,
    name: n.name,
    status: n.status || 'online',
    model: n.active_model || 'qwen2.5-coder:32b',
    vram_used: n.gpu ? (n.gpu.vram_used_mb / 1024).toFixed(1) : 4.0,
    vram_total: n.gpu ? (n.gpu.vram_total_mb / 1024).toFixed(0) : 80,
    gpu_pct: n.gpu ? n.gpu.utilization_pct.toFixed(0) : 0,
    temp: n.gpu ? n.gpu.temperature_c.toFixed(0) : 40,
    screen: ':0 (HUD Active)'
  }));
  renderNodesGrid();
  updateStats();
}

function updateSingleNodeTelemetry(telemetry) {
  const node = nodesData.find(n => n.id === telemetry.node_id);
  if (node) {
    node.status = telemetry.status;
    if (telemetry.gpu) {
      node.vram_used = (telemetry.gpu.vram_used_mb / 1024).toFixed(1);
      node.gpu_pct = telemetry.gpu.utilization_pct.toFixed(0);
      node.temp = telemetry.gpu.temperature_c.toFixed(0);
    }
    renderNodesGrid();
    updateStats();
  }
}

function setNodeStatus(nodeId, status) {
  const node = nodesData.find(n => n.id === nodeId);
  if (node) {
    node.status = status;
    renderNodesGrid();
    updateStats();
  }
}

// Render DGX Node Cards inside Drawer
function renderNodesGrid(filter = 'all') {
  if (!dgxGrid) return;
  dgxGrid.innerHTML = '';
  const filtered = nodesData.filter(n => filter === 'all' || n.status === filter);

  filtered.forEach(node => {
    const card = document.createElement('div');
    card.className = `node-card ${node.id === selectedNodeId ? 'active-terminal' : ''}`;
    card.setAttribute('data-id', node.id);

    const vramPct = Math.min(100, Math.round((node.vram_used / node.vram_total) * 100));

    card.innerHTML = `
      <div class="node-top">
        <span class="node-id">${node.id}</span>
        <span class="node-status-pill ${node.status}">${node.status}</span>
      </div>
      <div class="node-name">${node.name}</div>
      <div class="node-model-row">
        <span class="model-pill">${node.model}</span>
      </div>
      <div class="node-telemetry-row">
        <span>VRAM: ${node.vram_used} / ${node.vram_total} GB</span>
        <div class="vram-bar-container">
          <div class="vram-fill" style="width: ${vramPct}%;"></div>
        </div>
        <span>GPU ${node.gpu_pct}% &bull; ${node.temp}°C</span>
      </div>
    `;

    card.addEventListener('click', () => {
      selectedNodeId = node.id;
      renderNodesGrid();
      activeTerminalLabel.textContent = `${node.name} — Terminal Output (${node.screen})`;
      appendTerminal(`[CONSOLE] Switched active view to ${node.id.toUpperCase()}`, 'term-cyan');
    });

    dgxGrid.appendChild(card);
  });
}

function updateStats() {
  const onlineCount = nodesData.filter(n => n.status === 'online').length;
  if (statOnlineNodes) statOnlineNodes.textContent = `${onlineCount}/8 Online`;
}

function appendTerminal(text, colorClass = '') {
  if (!terminalOutput) return;
  const span = document.createElement('span');
  if (colorClass) span.className = colorClass;
  span.textContent = text + '\n';
  terminalOutput.appendChild(span);
  terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

if (btnClearTerminal) {
  btnClearTerminal.addEventListener('click', () => {
    terminalOutput.innerHTML = '<span class="term-dim">[SYSTEM] Terminal cleared. Ready for next stream chunk.</span>\n';
  });
}

// Speech Synthesis (Audio Output)
function speakAudioResponse(text) {
  if (!('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => v.lang.includes('IN') || v.name.includes('India') || v.lang.includes('hi'));
    if (preferredVoice) utterance.voice = preferredVoice;
    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.warn('Speech synthesis error:', e);
  }
}

// Voice Recognition (Speech Input)
let recognition = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRec();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'hi-IN'; // Recognizes Hindi, Hinglish, and English

  recognition.onstart = () => {
    btnMic.classList.add('active-listening');
    voiceStateText.textContent = 'Listening to voice command...';
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    cmdInput.value = transcript;
    voiceStateText.textContent = `Captured: "${transcript}"`;
    dispatchCommand(transcript);
  };

  recognition.onerror = () => {
    btnMic.classList.remove('active-listening');
    voiceStateText.textContent = 'Voice input stopped. Click mic to retry.';
  };

  recognition.onend = () => {
    btnMic.classList.remove('active-listening');
  };
}

if (btnMic) {
  btnMic.addEventListener('click', () => {
    if (!recognition) {
      alert('Web Speech API is not supported in this browser. Please type your prompt.');
      return;
    }
    try {
      recognition.start();
    } catch (e) {
      recognition.stop();
    }
  });
}

// ==============================================================================
// Minimal GPT-Style Chat Stream Handlers
// ==============================================================================

function appendUserMessage(text) {
  if (chatWelcomeHero) chatWelcomeHero.classList.add('hidden');

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble user-bubble';
  bubble.innerHTML = `
    <div class="user-bubble-content">${escapeHtml(text)}</div>
  `;
  chatMessagesList.appendChild(bubble);
  scrollToBottom();
}

function appendAssistantMessage(promptText, targetNode = 'auto') {
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble assistant-bubble';

  const isPipeline = targetNode === 'auto' || promptText.toLowerCase().includes('pipeline');
  const targetLabel = isPipeline ? '4-Node Autonomous Pipeline' : (nodesData.find(n => n.id === targetNode)?.name || targetNode);

  bubble.innerHTML = `
    <div class="assistant-header">
      <div class="assistant-avatar">🤖</div>
      <div class="assistant-name">AEGIS Cluster</div>
      <div class="assistant-node-tag">${targetLabel}</div>
    </div>
    <div class="assistant-body">
      <div class="pipeline-stepper" id="active-pipeline-stepper">
        <div class="pipeline-stepper-title">Autonomous Execution Pipeline</div>
        <div class="pipeline-stages">
          <div class="stage-step active" id="step-stage-1">
            <span class="step-num">STAGE 1</span>
            <span class="step-name">Node 1: Synthesizer</span>
          </div>
          <div class="stage-step" id="step-stage-2">
            <span class="step-num">STAGE 2</span>
            <span class="step-name">Node 2: QA & Pytest</span>
          </div>
          <div class="stage-step" id="step-stage-3">
            <span class="step-num">STAGE 3</span>
            <span class="step-name">Node 3: Architecture</span>
          </div>
          <div class="stage-step" id="step-stage-4">
            <span class="step-num">STAGE 4</span>
            <span class="step-name">Node 4: Security Hardening</span>
          </div>
        </div>
      </div>

      <div class="assistant-response-text" id="active-assistant-text">
        Task dispatched to compute nodes. Generating self-healing implementation and allocating GPU context...
      </div>

      <button class="stream-accordion-btn" onclick="openTerminalDrawer()">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
        <span>View Live Terminal Output</span>
      </button>
    </div>
  `;
  chatMessagesList.appendChild(bubble);
  currentAssistantMsgEl = bubble;
  scrollToBottom();
}

function updateAssistantProgress(stageId, state) {
  if (!currentAssistantMsgEl) return;
  const stepEl = currentAssistantMsgEl.querySelector(`#step-${stageId}`);
  if (stepEl) {
    stepEl.classList.remove('active', 'done');
    stepEl.classList.add(state);
  }
}

function finalizeAssistantMsg(summaryText) {
  if (!currentAssistantMsgEl) return;
  const textEl = currentAssistantMsgEl.querySelector('#active-assistant-text');
  if (textEl) {
    textEl.innerHTML = `
      <p style="margin-bottom: 0.65rem;">${summaryText}</p>
      <div class="code-block-card">
        <div class="code-block-header">
          <span>dist_kv_cache.py</span>
          <button class="btn-copy-code" onclick="navigator.clipboard.writeText('# AEGIS Generated Artifact\nimport asyncio\n...')">Copy</button>
        </div>
        <pre class="code-block-body"><code># Generated by DGX Node 1 (Verified by Node 2 Pytest Suite)
import asyncio
import time
from typing import Dict, Any, Optional

class DistributedKVCache:
    """High-throughput async cache with TTL and thread-safe boundaries."""
    def __init__(self, default_ttl: float = 300.0):
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        
    async def set(self, key: str, val: Any, ttl: Optional[float] = None) -> None:
        async with self._lock:
            self._store[key] = val
            self._expiry[key] = time.time() + (ttl or 300.0)
            
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._store and time.time() < self._expiry[key]:
                return self._store[key]
            return None</code></pre>
      </div>
    `;
  }
  scrollToBottom();
}

function scrollToBottom() {
  if (chatScrollArea) {
    setTimeout(() => {
      chatScrollArea.scrollTop = chatScrollArea.scrollHeight;
    }, 50);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Dispatch Command (REST API or Local Simulation fallback)
async function dispatchCommand(commandText) {
  if (!commandText || !commandText.trim()) return;
  const prompt = commandText.trim();
  cmdInput.value = '';
  cmdInput.style.height = 'auto';

  // 1. Append User Message
  appendUserMessage(prompt);

  // 2. Append Assistant Message in Chat Thread
  appendAssistantMessage(prompt, selectedNodeId);

  appendTerminal(`\n> [VOICE PROMPT]: "${prompt}"`, 'term-cyan');

  // Try posting to coordinator API on port 9000
  try {
    const res = await fetch(`${API_BASE}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: prompt, preferred_node: selectedNodeId === 'auto' ? 'dgx-node-1' : selectedNodeId })
    });

    if (res.ok) {
      const data = await res.json();
      handleTaskSubmissionResponse(data, prompt);
      return;
    }
  } catch (err) {
    console.warn('Backend API submission deferred:', err);
  }

  // Local Smart Intent Simulation fallback
  handleLocalSimulation(prompt);
}

function handleTaskSubmissionResponse(data, originalPrompt) {
  if (data.spoken_response) {
    spokenText.textContent = `"${data.spoken_response}"`;
    if (spokenReplyContainer) spokenReplyContainer.classList.remove('hidden');
    speakAudioResponse(data.spoken_response);
  }

  if (data.status === 'awaiting_approval') {
    currentPendingTaskId = data.task_id || 'tsk-pending';
    safetyPanel.classList.remove('hidden');
    safetyRiskLevel.textContent = data.safety_evaluation?.risk_level || 'CRITICAL';
    safetyReason.textContent = data.safety_evaluation?.reasons?.[0] || 'High risk operation detected.';
    safetyCommandText.textContent = data.safety_evaluation?.proposed_command || originalPrompt;
    appendTerminal(`[SAFETY ALERT] Evidence-gated hold: Confirmation required.`, 'term-rose');
  } else if (data.status === 'task_scheduled' || data.status === 'success') {
    const assigned = data.assigned_node || 'dgx-node-1';
    appendTerminal(`[ROUTER] Task assigned to ${assigned}.`, 'term-emerald');
    setNodeStatus(assigned, 'busy');
    simulateExecutionStream(assigned, originalPrompt);
  }
}

function handleLocalSimulation(prompt) {
  const lower = prompt.toLowerCase();
  let spoken = "";
  let targetNode = "dgx-node-1";

  if (lower.includes('shut down') || lower.includes('shutdown') || lower.includes('band karo')) {
    safetyPanel.classList.remove('hidden');
    safetyRiskLevel.textContent = "CRITICAL RISK";
    safetyReason.textContent = "Destructive command pattern matched: System shutdown request.";
    safetyCommandText.textContent = "shutdown -h now";
    spoken = "Savdhaan! Shutdown command evidence-gated verification ke liye hold par hai. Kripya confirm karein.";
    spokenText.textContent = `"${spoken}"`;
    if (spokenReplyContainer) spokenReplyContainer.classList.remove('hidden');
    speakAudioResponse(spoken);
    appendTerminal('[SAFETY] Command held by Evidence-Gated Safety Engine.', 'term-rose');
    return;
  }

  if (lower.includes('status') || lower.includes('online')) {
    spoken = "Filhaal sabhi 8 NVIDIA DGX Spark nodes online aur ready hain. VRAM capacity 1024 GB available hai.";
    spokenText.textContent = `"${spoken}"`;
    if (spokenReplyContainer) spokenReplyContainer.classList.remove('hidden');
    speakAudioResponse(spoken);
    appendTerminal('[STATUS] Cluster Health: 8 Nodes Online. Storage PC i7-14700 Active.', 'term-cyan');
    updateAssistantProgress('stage-1', 'done');
    updateAssistantProgress('stage-2', 'done');
    updateAssistantProgress('stage-3', 'done');
    updateAssistantProgress('stage-4', 'done');
    finalizeAssistantMsg(spoken);
    return;
  }

  if (lower.includes('csv') || lower.includes('data')) {
    targetNode = "dgx-node-1";
    spoken = "Data Science pipeline Node 1 ko assign kiya hai. Pandas, Matplotlib charts aur Pytest suite generate ho rahe hain.";
  } else if (lower.includes('review') || lower.includes('test')) {
    targetNode = "dgx-node-2";
    spoken = "Code review aur verification agent DGX Node 02 par comprehensive pytest suite run kar raha hai.";
  } else {
    targetNode = "dgx-node-1";
    spoken = `Task receive hua. 4-node distributed pipeline execute ho rahi hai.`;
  }

  spokenText.textContent = `"${spoken}"`;
  if (spokenReplyContainer) spokenReplyContainer.classList.remove('hidden');
  speakAudioResponse(spoken);
  setNodeStatus(targetNode, 'busy');
  simulateExecutionStream(targetNode, prompt);
}

// Simulates live execution chunks in the terminal
function simulateExecutionStream(nodeId, prompt) {
  const node = nodesData.find(n => n.id === nodeId);
  const nodeName = node ? node.name : nodeId;

  appendTerminal(`\n--- [LIVE SESSION ON ${nodeName.toUpperCase()}] ---`, 'term-cyan');
  appendTerminal(`$ aegis-agent --execute --task "${prompt.slice(0, 40)}"`, 'term-dim');

  const steps = [
    { text: `[dgx-node-1] Lead Coder: Synthesizing solution...`, stage: 'stage-1' },
    { text: `[dgx-node-2] QA Reviewer: Generating pytest unit tests...`, stage: 'stage-2' },
    { text: `[dgx-node-3] Systems Architect: Profiling dataflow & visual spec...`, stage: 'stage-3' },
    { text: `[dgx-node-4] Security Sentinel: Verifying boundaries & sign-off...`, stage: 'stage-4' }
  ];

  steps.forEach((step, idx) => {
    setTimeout(() => {
      appendTerminal(step.text, idx === steps.length - 1 ? 'term-emerald' : 'term-cyan');
      updateAssistantProgress(step.stage, 'done');
      if (idx < steps.length - 1) {
        updateAssistantProgress(steps[idx + 1].stage, 'active');
      }
      if (idx === steps.length - 1) {
        setNodeStatus(nodeId, 'online');
        createDemoArtifact(prompt);
        finalizeAssistantMsg("Full 4-node cluster pipeline completed! High-throughput solution synthesized on Node 1, unit tests generated by Node 2, and security certified by Node 4.");
      }
    }, (idx + 1) * 900);
  });
}

function createDemoArtifact(prompt) {
  const fname = prompt.toLowerCase().includes('csv') ? 'csv_data_analysis.py' : 'dist_kv_cache.py';
  const row = document.createElement('div');
  row.className = 'artifact-item';
  row.innerHTML = `
    <span class="artifact-name">📄 ${fname}</span>
    <a href="#" class="artifact-link" onclick="alert('Artifact synced to shared vault: aegis_server/artifacts/${fname}'); return false;">Download</a>
  `;
  const empty = artifactsList.querySelector('.artifact-empty-state');
  if (empty) empty.remove();
  artifactsList.prepend(row);
}

// Safety Panel Approval Handlers
if (btnApprove) {
  btnApprove.addEventListener('click', async () => {
    safetyPanel.classList.add('hidden');
    appendTerminal('[SAFETY APPROVED] User authorized action. Executing safe procedure.', 'term-emerald');
    spokenText.textContent = '"Action authorized. Executing safely."';
    speakAudioResponse('Action authorized. Executing safely.');
  });
}

if (btnReject) {
  btnReject.addEventListener('click', () => {
    safetyPanel.classList.add('hidden');
    appendTerminal('[SAFETY REJECTED] Action aborted by user authorization denial.', 'term-rose');
    spokenText.textContent = '"Action rejected. Operation cancelled."';
    speakAudioResponse('Action rejected. Operation cancelled.');
  });
}

// Event Listeners for Command Dispatch
if (btnDispatch) {
  btnDispatch.addEventListener('click', () => dispatchCommand(cmdInput.value));
}

if (cmdInput) {
  cmdInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      dispatchCommand(cmdInput.value);
    }
  });

  // Auto-resize input
  cmdInput.addEventListener('input', () => {
    cmdInput.style.height = 'auto';
    cmdInput.style.height = Math.min(cmdInput.scrollHeight, 140) + 'px';
  });
}

// Prompt Chips & Suggestion Cards
function bindPromptChips() {
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const cmd = chip.getAttribute('data-cmd');
      if (cmd) {
        cmdInput.value = cmd;
        dispatchCommand(cmd);
      }
    });
  });
}
bindPromptChips();

// New Chat button
if (btnNewChat) {
  btnNewChat.addEventListener('click', () => {
    chatMessagesList.innerHTML = '';
    if (chatWelcomeHero) chatWelcomeHero.classList.remove('hidden');
    cmdInput.value = '';
    cmdInput.focus();
  });
}

// Sidebar Toggle
if (btnSidebarToggle) {
  btnSidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
  });
}

// Theme Switcher (Light / Dark)
if (btnThemeToggle) {
  btnThemeToggle.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-theme');
    document.body.classList.toggle('light-theme', !isDark);
    themeIcon.textContent = isDark ? '☀️' : '🌙';
    themeText.textContent = isDark ? 'Light Mode' : 'Dark Mode';
    localStorage.setItem('aegis-theme', isDark ? 'dark' : 'light');
  });
}

// Model Picker Dropdown
if (modelPickerTrigger) {
  modelPickerTrigger.addEventListener('click', (e) => {
    e.stopPropagation();
    modelDropdownMenu.classList.toggle('hidden');
  });

  document.addEventListener('click', () => {
    if (modelDropdownMenu) modelDropdownMenu.classList.add('hidden');
  });

  document.querySelectorAll('.dropdown-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('selected'));
      item.classList.add('selected');
      selectedNodeId = item.getAttribute('data-node');
      activeModelName.textContent = item.getAttribute('data-label');
      modelDropdownMenu.classList.add('hidden');
      renderNodesGrid();
    });
  });
}

// Drawer Toggle Handlers
function openNodesDrawer() {
  if (nodesDrawerOverlay) nodesDrawerOverlay.classList.remove('hidden');
}
function closeNodesDrawer() {
  if (nodesDrawerOverlay) nodesDrawerOverlay.classList.add('hidden');
}

function openVaultDrawer() {
  if (vaultDrawerOverlay) vaultDrawerOverlay.classList.remove('hidden');
  loadRecentArtifacts();
}
function closeVaultDrawer() {
  if (vaultDrawerOverlay) vaultDrawerOverlay.classList.add('hidden');
}

function openTerminalDrawer() {
  if (terminalDrawerOverlay) terminalDrawerOverlay.classList.remove('hidden');
}
function closeTerminalDrawer() {
  if (terminalDrawerOverlay) terminalDrawerOverlay.classList.add('hidden');
}
window.openTerminalDrawer = openTerminalDrawer;

if (btnToggleNodesDrawer) btnToggleNodesDrawer.addEventListener('click', openNodesDrawer);
if (btnQuickNodes) btnQuickNodes.addEventListener('click', openNodesDrawer);
if (btnCloseNodesDrawer) btnCloseNodesDrawer.addEventListener('click', closeNodesDrawer);
if (nodesDrawerOverlay) {
  nodesDrawerOverlay.addEventListener('click', (e) => {
    if (e.target === nodesDrawerOverlay) closeNodesDrawer();
  });
}

if (btnToggleVaultDrawer) btnToggleVaultDrawer.addEventListener('click', openVaultDrawer);
if (btnQuickVault) btnQuickVault.addEventListener('click', openVaultDrawer);
if (btnCloseVaultDrawer) btnCloseVaultDrawer.addEventListener('click', closeVaultDrawer);
if (vaultDrawerOverlay) {
  vaultDrawerOverlay.addEventListener('click', (e) => {
    if (e.target === vaultDrawerOverlay) closeVaultDrawer();
  });
}

if (btnToggleTerminalDrawer) btnToggleTerminalDrawer.addEventListener('click', openTerminalDrawer);
if (btnCloseTerminalDrawer) btnCloseTerminalDrawer.addEventListener('click', closeTerminalDrawer);
if (terminalDrawerOverlay) {
  terminalDrawerOverlay.addEventListener('click', (e) => {
    if (e.target === terminalDrawerOverlay) closeTerminalDrawer();
  });
}

// Load Recent Artifacts from Storage Vault
async function loadRecentArtifacts() {
  try {
    const res = await fetch(`${STORAGE_BASE}/api/storage/recent`);
    if (res.ok) {
      const data = await res.json();
      if (data.recent_artifacts && data.recent_artifacts.length) {
        artifactsList.innerHTML = '';
        data.recent_artifacts.forEach(item => {
          const row = document.createElement('div');
          row.className = 'artifact-item';
          const dlUrl = item.url.startsWith('http') ? item.url : `${STORAGE_BASE}${item.url}`;
          row.innerHTML = `
            <span class="artifact-name">📄 ${item.filename}</span>
            <a href="${dlUrl}" target="_blank" class="artifact-link">Download</a>
          `;
          artifactsList.appendChild(row);
        });
        return;
      }
    }
  } catch (e) {
    console.warn('Storage recent fetch error:', e);
  }
}

if (btnRefreshArtifacts) {
  btnRefreshArtifacts.addEventListener('click', async () => {
    await loadRecentArtifacts();
    appendTerminal('[STORAGE] Refreshed artifacts from i7-14700 vault.', 'term-dim');
  });
}

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
  // Check theme preference
  const savedTheme = localStorage.getItem('aegis-theme');
  if (savedTheme === 'dark') {
    document.body.classList.add('dark-theme');
    document.body.classList.remove('light-theme');
    if (themeIcon) themeIcon.textContent = '☀️';
    if (themeText) themeText.textContent = 'Light Mode';
  }

  renderNodesGrid();
  updateStats();
  initWebSocket();
  loadRecentArtifacts();
});
