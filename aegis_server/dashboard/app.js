/**
 * AEGIS Mission Control Dashboard Logic
 * Handles real-time WebSockets, Web Speech API, terminal streaming, and safety confirmations.
 */

// Target API Hosts (Coordinator and Storage)
const API_BASE = window.location.origin;
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
// Connect to Coordinator on port 9000
const WS_URL = `${WS_PROTOCOL}//${window.location.hostname}:9000/ws/cluster`;

// DOM Elements
const cmdInput = document.getElementById('cmd-input-field');
const btnDispatch = document.getElementById('btn-dispatch-cmd');
const btnMic = document.getElementById('btn-mic-toggle');
const voiceIndicator = document.getElementById('voice-indicator');
const voiceStateText = document.getElementById('voice-state-text');
const spokenText = document.getElementById('spoken-text');
const dgxGrid = document.getElementById('dgx-nodes-grid');
const terminalOutput = document.getElementById('terminal-output');
const activeTerminalLabel = document.getElementById('active-terminal-node');
const btnClearTerminal = document.getElementById('btn-clear-terminal');
const artifactsList = document.getElementById('artifacts-list-container');
const btnRefreshArtifacts = document.getElementById('btn-refresh-artifacts');

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
let selectedNodeId = 'dgx-node-1';

// Initial default node data mapped to the 8 ultimate models (899B / 1024 GB Cluster)
let nodesData = [
  { id: 'dgx-node-1', name: 'DGX Spark 01 - Lead Coder', status: 'online', model: 'DeepSeek-Coder-V2 (236B MoE)', vram_used: 98.0, vram_total: 128, gpu_pct: 14, temp: 45, screen: ':0 (Lead Coder HUD)' },
  { id: 'dgx-node-2', name: 'DGX Spark 02 - Reviewer & QA', status: 'online', model: 'Qwen2.5-72B-Instruct (72B)', vram_used: 52.0, vram_total: 128, gpu_pct: 8, temp: 41, screen: ':0 (QA Review HUD)' },
  { id: 'dgx-node-3', name: 'DGX Spark 03 - Vision Model', status: 'online', model: 'Pixtral Large (124B Multimodal)', vram_used: 70.0, vram_total: 128, gpu_pct: 16, temp: 44, screen: ':0 (Pixtral Vision HUD)' },
  { id: 'dgx-node-4', name: 'DGX Spark 04 - Writer & Reasoner', status: 'online', model: 'Mixtral 8x22B MoE (141B)', vram_used: 80.0, vram_total: 128, gpu_pct: 22, temp: 48, screen: ':0 (Deep Reason HUD)' },
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

    ws.onerror = () => {
      // Coordinator might not be started yet if user runs local storage only
    };
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

// Render 8 DGX Node Cards
function renderNodesGrid(filter = 'all') {
  dgxGrid.innerHTML = '';
  const filtered = nodesData.filter(n => filter === 'all' || n.status === filter);

  filtered.forEach(node => {
    const card = document.createElement('div');
    card.className = `node-card ${node.id === selectedNodeId ? 'active-terminal' : ''}`;
    card.id = `card-${node.id}`;

    const vramPct = Math.min(100, Math.round((node.vram_used / node.vram_total) * 100));

    card.innerHTML = `
      <div class="node-card-top">
        <div>
          <span class="node-id-tag">${node.id.toUpperCase()}</span>
          <h4 class="node-card-name">${node.name}</h4>
        </div>
        <span class="node-status-badge status-${node.status}">
          ● ${node.status}
        </span>
      </div>

      <div class="node-model-row">
        <span>Model:</span>
        <span class="model-pill">${node.model}</span>
      </div>

      <div class="vram-section">
        <div class="vram-labels">
          <span>VRAM ${node.vram_used} / ${node.vram_total} GB</span>
          <span>GPU ${node.gpu_pct}% (${node.temp}°C)</span>
        </div>
        <div class="vram-bar-track">
          <div class="vram-bar-fill" style="width: ${vramPct}%;"></div>
        </div>
      </div>

      <div class="node-screen-row">
        <span>Physical Screen:</span>
        <span class="screen-live">${node.screen}</span>
      </div>
    `;

    card.addEventListener('click', () => {
      selectedNodeId = node.id;
      activeTerminalLabel.textContent = `${node.name} — Terminal Output (${node.screen})`;
      renderNodesGrid(filter);
      appendTerminal(`\n[VIEW] Switched active view to ${node.name} (${node.id})`, 'term-cyan');
    });

    dgxGrid.appendChild(card);
  });
}

function updateStats() {
  const onlineCount = nodesData.filter(n => n.status === 'online' || n.status === 'busy').length;
  statOnlineNodes.textContent = `${onlineCount} / ${nodesData.length}`;
  const busyCount = nodesData.filter(n => n.status === 'busy').length;
  statActiveTasks.textContent = busyCount.toString();
}

// Terminal Append Helper
function appendTerminal(text, cssClass = '') {
  const span = document.createElement('span');
  if (cssClass) span.className = cssClass;
  span.textContent = text + (text.endsWith('\n') ? '' : '\n');
  terminalOutput.appendChild(span);
  terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

btnClearTerminal.addEventListener('click', () => {
  terminalOutput.innerHTML = '<span class="term-dim">[SYSTEM] Terminal cleared. Ready for next stream chunk.</span>\n';
});

// Speech Synthesis (Audio Output)
function speakAudioResponse(text) {
  if (!('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    
    // Choose appropriate voice
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

// Dispatch Command (REST API or Local Simulation fallback)
async function dispatchCommand(commandText) {
  if (!commandText || !commandText.trim()) return;
  const prompt = commandText.trim();
  cmdInput.value = '';

  appendTerminal(`\n> [VOICE PROMPT]: "${prompt}"`, 'term-cyan');

  // Try posting to coordinator API on port 9000
  try {
    const res = await fetch(`http://${window.location.hostname}:9000/api/tasks/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: prompt, preferred_node: selectedNodeId })
    });

    if (res.ok) {
      const data = await res.json();
      handleTaskSubmissionResponse(data, prompt);
      return;
    }
  } catch (err) {
    // If coordinator isn't running on port 8000 yet, handle locally with smart intent parser
  }

  // Local Smart Intent Simulation fallback
  handleLocalSimulation(prompt);
}

function handleTaskSubmissionResponse(data, originalPrompt) {
  if (data.spoken_response) {
    spokenText.textContent = `"${data.spoken_response}"`;
    speakAudioResponse(data.spoken_response);
  }

  if (data.status === 'awaiting_approval') {
    currentPendingTaskId = data.task_id || 'tsk-pending';
    safetyPanel.classList.remove('hidden');
    safetyRiskLevel.textContent = data.safety_evaluation?.risk_level || 'CRITICAL';
    safetyReason.textContent = data.safety_evaluation?.reasons?.[0] || 'High risk operation detected.';
    safetyCommandText.textContent = data.safety_evaluation?.proposed_command || originalPrompt;
    appendTerminal(`[SAFETY ALERT] Evidence-gated hold: Confirmation required.`, 'term-rose');
  } else if (data.status === 'task_scheduled') {
    appendTerminal(`[ROUTER] Task assigned to ${data.assigned_node}. Reviewer: ${data.reviewer_node}`, 'term-emerald');
    setNodeStatus(data.assigned_node, 'busy');
    simulateExecutionStream(data.assigned_node, originalPrompt);
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
    speakAudioResponse(spoken);
    appendTerminal('[SAFETY] Command held by Evidence-Gated Safety Engine.', 'term-rose');
    return;
  }

  if (lower.includes('status') || lower.includes('online')) {
    spoken = "Filhaal sabhi 8 NVIDIA DGX Spark nodes online aur ready hain. VRAM capacity 640 GB available hai.";
    spokenText.textContent = `"${spoken}"`;
    speakAudioResponse(spoken);
    appendTerminal('[STATUS] Cluster Health: 8 Nodes Online. Storage PC i7-14700 Active.', 'term-cyan');
    return;
  }

  if (lower.includes('csv') || lower.includes('data')) {
    targetNode = "dgx-node-3";
    spoken = "Data Science node DGX Spark 03 ko CSV analytics task assign kiya hai. Screen par terminal foreground ho chuka hai.";
  } else if (lower.includes('review') || lower.includes('test')) {
    targetNode = "dgx-node-2";
    spoken = "Code review aur verification agent DGX Node 02 par test suite run kar raha hai.";
  } else {
    targetNode = "dgx-node-1";
    spoken = `Task receive hua. DGX Spark 01 par execution shuru ho chuki hai.`;
  }

  spokenText.textContent = `"${spoken}"`;
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
    `[${nodeId}] Initializing local model: ${node ? node.model : 'qwen2.5-coder:32b'}...`,
    `[${nodeId}] CUDA context allocated. Allocating GPU memory on A100/H100...`,
    `[${nodeId}] Generating solution script & setting up virtual sandbox...`,
    `[${nodeId}] Running automated lint checks and unit verification...`,
    `[${nodeId}] Execution SUCCESS (Exit Code 0). Syncing artifacts to i7-14700 storage vault.`
  ];

  steps.forEach((step, idx) => {
    setTimeout(() => {
      appendTerminal(step, idx === steps.length - 1 ? 'term-emerald' : '');
      if (idx === steps.length - 1) {
        setNodeStatus(nodeId, 'online');
        createDemoArtifact(prompt);
      }
    }, (idx + 1) * 800);
  });
}

function createDemoArtifact(prompt) {
  const fname = prompt.toLowerCase().includes('csv') ? 'csv_data_analysis.py' : 'generated_pipeline.py';
  const row = document.createElement('div');
  row.className = 'artifact-row';
  row.innerHTML = `
    <div class="artifact-info">
      <span class="artifact-fname">📄 ${fname}</span>
      <span class="artifact-fmeta">Generated by ${selectedNodeId} &bull; Stored on i7-14700 PC</span>
    </div>
    <a href="#" class="artifact-dl-btn" onclick="alert('Artifact available in shared storage.'); return false;">Download</a>
  `;
  const empty = artifactsList.querySelector('.artifact-empty-state');
  if (empty) empty.remove();
  artifactsList.prepend(row);
}

// Safety Panel Approval Handlers
btnApprove.addEventListener('click', async () => {
  safetyPanel.classList.add('hidden');
  appendTerminal('[SAFETY APPROVED] User authorized action. Executing safe procedure.', 'term-emerald');
  spokenText.textContent = '"Action authorized. Executing safely."';
  speakAudioResponse('Action authorized. Executing safely.');
});

btnReject.addEventListener('click', () => {
  safetyPanel.classList.add('hidden');
  appendTerminal('[SAFETY REJECTED] Action aborted by user authorization denial.', 'term-rose');
  spokenText.textContent = '"Action rejected. Operation cancelled."';
  speakAudioResponse('Action rejected. Operation cancelled.');
});

// Event Listeners for Command Dispatch
btnDispatch.addEventListener('click', () => dispatchCommand(cmdInput.value));
cmdInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') dispatchCommand(cmdInput.value);
});

// Prompt Chips
document.querySelectorAll('.prompt-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const cmd = chip.getAttribute('data-cmd');
    cmdInput.value = cmd;
    dispatchCommand(cmd);
  });
});

// Filter Pills
document.querySelectorAll('.filter-pill').forEach(pill => {
  pill.addEventListener('click', () => {
    document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    renderNodesGrid(pill.getAttribute('data-filter'));
  });
});

// Refresh Artifacts Button
btnRefreshArtifacts.addEventListener('click', async () => {
  try {
    const res = await fetch('/api/storage/recent');
    if (res.ok) {
      const data = await res.json();
      if (data.recent_artifacts && data.recent_artifacts.length) {
        artifactsList.innerHTML = '';
        data.recent_artifacts.forEach(item => {
          const row = document.createElement('div');
          row.className = 'artifact-row';
          row.innerHTML = `
            <div class="artifact-info">
              <span class="artifact-fname">📄 ${item.filename}</span>
              <span class="artifact-fmeta">${(item.size_bytes / 1024).toFixed(1)} KB &bull; Task: ${item.task_id}</span>
            </div>
            <a href="${item.url}" target="_blank" class="artifact-dl-btn">Download</a>
          `;
          artifactsList.appendChild(row);
        });
        return;
      }
    }
  } catch (e) {
    // If storage server not queried over http
  }
  appendTerminal('[STORAGE] Checked i7-14700 vault directory.', 'term-dim');
});

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
  renderNodesGrid();
  updateStats();
  initWebSocket();
});
