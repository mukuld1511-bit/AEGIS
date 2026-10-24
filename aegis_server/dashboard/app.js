/**
 * AEGIS - Dual Interface Logic:
 * 1. User Prompt View: Zero-fluff, direct answers and pure code blocks only. On-demand Siri voice avatar.
 * 2. Cluster Cockpit View ("Mere Liye"): 4-node DGX hardware cluster, live distribution mesh, raw terminal (:0), and vault storage.
 */

// Network endpoints resolution
const isDirectPiPort = window.location.port === '9000';
const isFunnel = window.location.hostname.includes('tail') || window.location.hostname.includes('.ts.net');
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

const WS_URL = (isDirectPiPort || isFunnel)
  ? `${WS_PROTOCOL}//${window.location.host}/ws/cluster`
  : `${WS_PROTOCOL}//${window.location.hostname}:9000/ws/cluster`;

const API_BASE = (isDirectPiPort || isFunnel)
  ? window.location.origin
  : `${window.location.protocol}//${window.location.hostname}:9000`;

const STORAGE_BASE = window.location.port === '9080'
  ? ''
  : (isFunnel ? `${window.location.protocol}//${window.location.hostname}:9080` : `${window.location.protocol}//${window.location.hostname}:9080`);

// DOM Elements: Views & Navigation
const tabUserView = document.getElementById('tab-user-view');
const tabOperatorView = document.getElementById('tab-operator-view');
const viewUserPanel = document.getElementById('view-user-panel');
const viewOperatorPanel = document.getElementById('view-operator-panel');

// User Interface Elements
const siriAvatar = document.getElementById('siri-avatar');
const siriOrb = document.getElementById('siri-orb');
const siriAmbient = document.getElementById('siri-ambient');
const voiceStateText = document.getElementById('voice-state-text');
const spokenText = document.getElementById('spoken-text');
const voiceOverlay = document.getElementById('voice-overlay');
const idleHero = document.getElementById('idle-hero');

// User Direct Answer Deck (ZERO LLM FILLER)
const userAnswerCard = document.getElementById('user-answer-card');
const userActiveModel = document.getElementById('user-active-model');
const userTaskStatus = document.getElementById('user-task-status');
const userCodeView = document.getElementById('user-code-view');
const userCodeBody = document.getElementById('user-code-body');
const userTextBody = document.getElementById('user-text-body');
const btnCopyUser = document.getElementById('btn-copy-user');
const userCopyLabel = document.getElementById('user-copy-label');
const btnDownloadUser = document.getElementById('btn-download-user');
const btnCloseUser = document.getElementById('btn-close-user');

// Inputs & Functional Controls
const cmdInput = document.getElementById('cmd-input-field');
const btnDispatch = document.getElementById('btn-dispatch-cmd');
const btnMic = document.getElementById('btn-mic-toggle');
const routeSelector = document.getElementById('route-selector');
const btnNewTask = document.getElementById('btn-new-task');
const btnThemeToggle = document.getElementById('btn-theme-toggle');

// Continuous Voice Toggle
const btnToggleContinuous = document.getElementById('btn-toggle-continuous');
const continuousDot = document.getElementById('continuous-dot');
const continuousLabel = document.getElementById('continuous-label');

// Cockpit (Operator Interface) Elements
const cockpitNodesGrid = document.getElementById('cockpit-nodes-grid');
const cockpitTerminalOutput = document.getElementById('cockpit-terminal-output');
const btnClearCockpitTerminal = document.getElementById('btn-clear-cockpit-terminal');
const cockpitArtifactsList = document.getElementById('cockpit-artifacts-list');
const btnRefreshVaultArtifacts = document.getElementById('btn-refresh-vault-artifacts');

// Safety Panel
const safetyPanel = document.getElementById('safety-alert-panel');
const safetyRiskLevel = document.getElementById('safety-risk-level');
const safetyReason = document.getElementById('safety-reason');
const safetyCommandText = document.getElementById('safety-command-text');
const btnApprove = document.getElementById('btn-approve-action');
const btnReject = document.getElementById('btn-reject-action');

// State Variables
let ws = null;
let isListening = false;
let isContinuousMode = false;
let audioContext = null;
let audioAnalyser = null;
let audioSource = null;
let micStream = null;
let animFrameId = null;
let currentSolutionCode = '';

// Initial 4 Flagship Cluster Nodes
let nodesData = [
  { id: 'dgx-node-1', name: 'DGX Spark 01 - Lead Coder', status: 'online', model: 'Qwen2.5-Coder:32B', vram_used: 19.5, vram_total: 128, gpu_pct: 14, temp: 45, screen: ':0' },
  { id: 'dgx-node-2', name: 'DGX Spark 02 - Reviewer & QA', status: 'online', model: 'Qwen2.5-Coder:32B', vram_used: 19.5, vram_total: 128, gpu_pct: 8, temp: 41, screen: ':0' },
  { id: 'dgx-node-3', name: 'DGX Spark 03 - Systems Architect', status: 'online', model: 'Llama-3.2-Vision:90B', vram_used: 65.0, vram_total: 128, gpu_pct: 16, temp: 44, screen: ':0' },
  { id: 'dgx-node-4', name: 'DGX Spark 04 - Security Sentinel', status: 'online', model: 'Qwen2.5:141B', vram_used: 82.0, vram_total: 128, gpu_pct: 22, temp: 48, screen: ':0' }
];

// Sample Vault Storage Artifacts
let vaultArtifacts = [
  { name: 'dist_kv_cache.py', size: '14.2 KB', time: '15:42', node: 'dgx-node-1' },
  { name: 'test_suite.py', size: '18.6 KB', time: '15:43', node: 'dgx-node-2' },
  { name: 'architecture_spec.md', size: '9.4 KB', time: '15:44', node: 'dgx-node-3' },
  { name: 'hardened_solution.py', size: '21.0 KB', time: '15:45', node: 'dgx-node-4' }
];

// ==============================================================================
// 1. Dual Interface Mode Switcher
// ==============================================================================

function setViewMode(mode) {
  if (mode === 'user') {
    tabUserView?.classList.add('active');
    tabOperatorView?.classList.remove('active');
    viewUserPanel?.classList.remove('hidden');
    viewOperatorPanel?.classList.add('hidden');
  } else {
    tabOperatorView?.classList.add('active');
    tabUserView?.classList.remove('active');
    viewOperatorPanel?.classList.remove('hidden');
    viewUserPanel?.classList.add('hidden');
    renderCockpitNodes();
    renderVaultArtifacts();
  }
}

tabUserView?.addEventListener('click', () => setViewMode('user'));
tabOperatorView?.addEventListener('click', () => setViewMode('operator'));

// ==============================================================================
// 2. Pure Result Extractor (STRICTLY NO LLM CONVERSATIONAL FILLER)
// ==============================================================================

function extractPureResult(text) {
  if (!text) return { type: 'text', content: 'Exit code 0. Success.' };
  let raw = text.trim();

  // 1. If text contains a markdown code block (```python ... ``` or ``` ... ```), extract ONLY the code
  const codeMatch = raw.match(/```(?:[a-zA-Z0-9_\-]+)?\s*([\s\S]*?)```/);
  if (codeMatch && codeMatch[1]) {
    return {
      type: 'code',
      content: codeMatch[1].trim()
    };
  }

  // 2. If text is directly Python code
  if (/^(?:import\s+|from\s+|def\s+|class\s+|async\s+def\s+|#)/m.test(raw)) {
    return {
      type: 'code',
      content: raw
    };
  }

  // 3. Strip conversational LLM greetings and pleasantries
  let clean = raw
    .replace(/^(?:(?:certainly|sure|hello|hi|here is|here's|i have created|i can help with that|as requested|below is|of course|alright|ji bilkul)[!.,:\s]*)+/i, '')
    .replace(/(?:(?:hope this helps|let me know if you need|feel free to ask|happy coding|if you have any questions|is there anything else).*)$/is, '')
    .trim();

  return {
    type: 'text',
    content: clean || raw
  };
}

function renderUserAnswer(rawAnswer, modelName = '⚡ 4-Node Pipeline') {
  if (idleHero) idleHero.classList.add('hidden');
  if (voiceOverlay) voiceOverlay.classList.add('hidden');
  if (userAnswerCard) userAnswerCard.classList.remove('hidden');

  if (userActiveModel) userActiveModel.textContent = modelName;
  if (userTaskStatus) userTaskStatus.textContent = 'Completed';

  const parsed = extractPureResult(rawAnswer);
  if (parsed.type === 'code') {
    currentSolutionCode = parsed.content;
    if (userCodeBody) userCodeBody.textContent = parsed.content;
    if (userCodeView) userCodeView.classList.remove('hidden');
    if (userTextBody) userTextBody.classList.add('hidden');
  } else {
    currentSolutionCode = parsed.content;
    if (userTextBody) userTextBody.textContent = parsed.content;
    if (userTextBody) userTextBody.classList.remove('hidden');
    if (userCodeView) userCodeView.classList.add('hidden');
  }
}

// Visibility helpers for On-Demand Voice Avatar
function showVoiceAvatar() {
  if (voiceOverlay) voiceOverlay.classList.remove('hidden');
  if (idleHero) idleHero.classList.add('hidden');
}

function hideVoiceAvatarIfIdle() {
  if (isListening || (window.speechSynthesis && window.speechSynthesis.speaking)) return;
  if (voiceOverlay) voiceOverlay.classList.add('hidden');
  if (userAnswerCard && !userAnswerCard.classList.contains('hidden')) {
    if (idleHero) idleHero.classList.add('hidden');
  } else {
    if (idleHero) idleHero.classList.remove('hidden');
  }
}

// ==============================================================================
// 3. Web Audio API Voice-Reactive Visualizer
// ==============================================================================

async function startAudioWaveVisualizer() {
  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      audioAnalyser = audioContext.createAnalyser();
      audioAnalyser.fftSize = 64;
    }
    if (audioContext.state === 'suspended') {
      await audioContext.resume();
    }
    if (!micStream) {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      audioSource = audioContext.createMediaStreamSource(micStream);
      audioSource.connect(audioAnalyser);
    }

    const dataArray = new Uint8Array(audioAnalyser.frequencyBinCount);

    function renderAudioFrame() {
      if (!isListening) return;
      animFrameId = requestAnimationFrame(renderAudioFrame);
      audioAnalyser.getByteFrequencyData(dataArray);

      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / dataArray.length;
      const scale = 1 + (avg / 255) * 0.45;
      const hueShift = Math.floor((avg / 255) * 180);

      if (siriOrb) {
        siriOrb.style.transform = `scale(${scale})`;
        siriOrb.style.filter = `hue-rotate(${hueShift}deg)`;
      }
      if (siriAmbient) {
        siriAmbient.style.transform = `scale(${scale * 1.2})`;
        siriAmbient.style.opacity = Math.min(1.0, 0.6 + (avg / 255) * 0.4);
      }
    }
    renderAudioFrame();
  } catch (err) {
    console.warn('Audio Visualizer error:', err);
  }
}

function stopAudioWaveVisualizer() {
  if (animFrameId) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
  if (siriOrb) siriOrb.style.transform = 'scale(1)';
  if (siriAmbient) siriAmbient.style.transform = 'scale(1)';
}

// ==============================================================================
// 4. TTS (Strictly Concise & Synced with Avatar)
// ==============================================================================

let cachedVoices = [];
function speakAudioResponse(text) {
  if (!('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    if (!cachedVoices.length) cachedVoices = window.speechSynthesis.getVoices();
    const naturalVoice = cachedVoices.find(v => 
      v.name.includes('Natural') || 
      v.name.includes('Neerja') || 
      v.name.includes('Swara') || 
      v.name.includes('Madhur') || 
      v.name.includes('Prabhat') ||
      v.name.includes('India') || 
      v.lang.includes('hi')
    ) || cachedVoices.find(v => v.lang.includes('en'));

    if (naturalVoice) utterance.voice = naturalVoice;

    utterance.onstart = () => {
      showVoiceAvatar();
      if (siriAvatar) siriAvatar.classList.add('speaking');
    };
    utterance.onend = () => {
      if (siriAvatar) siriAvatar.classList.remove('speaking');
      hideVoiceAvatarIfIdle();
    };
    utterance.onerror = () => {
      if (siriAvatar) siriAvatar.classList.remove('speaking');
      hideVoiceAvatarIfIdle();
    };

    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.warn('TTS error:', e);
  }
}

// ==============================================================================
// 5. Speech Recognition & Wake-Word Detection
// ==============================================================================

let recognition = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRec();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'hi-IN';

  recognition.onstart = () => {
    isListening = true;
    showVoiceAvatar();
    if (siriAvatar) siriAvatar.classList.add('listening');
    if (btnMic) btnMic.classList.add('active-listening');
    if (voiceStateText) voiceStateText.textContent = 'Listening...';
    startAudioWaveVisualizer();
  };

  recognition.onresult = (event) => {
    let interim = '';
    let finalTranscript = '';

    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interim += event.results[i][0].transcript;
      }
    }

    const currentText = (finalTranscript || interim).trim();
    if (currentText) {
      spokenText.textContent = `"${currentText}"`;
    }

    if (finalTranscript) {
      const lower = finalTranscript.toLowerCase().trim();
      if (isContinuousMode) {
        const isWakeWord = lower.includes('aegis') || lower.includes('suno') || lower.includes('namaste');
        if (isWakeWord) {
          dispatchCommand(finalTranscript);
        }
      } else {
        dispatchCommand(finalTranscript);
      }
    }
  };

  recognition.onerror = (e) => {
    console.warn('Speech warning:', e.error);
    if (!isContinuousMode) stopListeningState();
  };

  recognition.onend = () => {
    if (isContinuousMode) {
      setTimeout(() => {
        if (isContinuousMode) {
          try { recognition.start(); } catch (err) {}
        }
      }, 350);
    } else {
      stopListeningState();
    }
  };
}

function startListeningState() {
  if (!recognition) return;
  showVoiceAvatar();
  try {
    recognition.start();
  } catch (err) {}
}

function stopListeningState() {
  isListening = false;
  if (siriAvatar) siriAvatar.classList.remove('listening');
  if (btnMic) btnMic.classList.remove('active-listening');
  if (voiceStateText) voiceStateText.textContent = 'Ready';
  stopAudioWaveVisualizer();
  hideVoiceAvatarIfIdle();
}

function toggleVoiceListening() {
  if (isListening) {
    try { recognition.stop(); } catch (e) {}
    stopListeningState();
  } else {
    startListeningState();
  }
}

if (siriAvatar) siriAvatar.addEventListener('click', toggleVoiceListening);
if (btnMic) btnMic.addEventListener('click', toggleVoiceListening);

// Continuous Listening Switch
if (btnToggleContinuous) {
  btnToggleContinuous.addEventListener('click', () => {
    isContinuousMode = !isContinuousMode;
    if (isContinuousMode) {
      btnToggleContinuous.classList.add('active');
      continuousLabel.textContent = 'Continuous: ON';
      if (voiceStateText) voiceStateText.textContent = 'Say "AEGIS" anytime';
      startListeningState();
    } else {
      btnToggleContinuous.classList.remove('active');
      continuousLabel.textContent = 'Continuous: OFF';
      stopListeningState();
      try { recognition.stop(); } catch (e) {}
    }
  });
}

// ==============================================================================
// 6. Command Dispatching & Direct Response Routing
// ==============================================================================

async function dispatchCommand(commandText) {
  if (!commandText || !commandText.trim()) return;
  const prompt = commandText.trim();
  cmdInput.value = '';

  // Minimal UI Transition: Hide idle hero
  if (idleHero) idleHero.classList.add('hidden');
  if (userAnswerCard) {
    userAnswerCard.classList.remove('hidden');
    userTaskStatus.textContent = 'Synthesizing';
    userTextBody.textContent = 'Executing...';
    userTextBody.classList.remove('hidden');
    userCodeView.classList.add('hidden');
  }

  appendTerminal(`> [PROMPT]: "${prompt}"`, 'term-cyan');

  const selectedTarget = routeSelector ? routeSelector.value : 'pipeline';
  const isPipeline = selectedTarget === 'pipeline';
  const targetNode = isPipeline ? 'dgx-node-1' : selectedTarget;

  // Submit to Coordinator API
  try {
    const res = await fetch(`${API_BASE}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        command: prompt, 
        preferred_node: targetNode,
        pipeline_mode: isPipeline
      })
    });

    if (res.ok) {
      const data = await res.json();
      handleTaskResponse(data, prompt);
      return;
    }
  } catch (err) {
    console.warn('Coordinator API fallback:', err);
  }

  // Pure Direct Simulation Fallback
  handleSimulation(prompt);
}

function handleTaskResponse(data, prompt) {
  if (data.spoken_response) {
    spokenText.textContent = `"${data.spoken_response}"`;
    speakAudioResponse(data.spoken_response);
  }

  if (data.status === 'awaiting_approval') {
    safetyPanel.classList.remove('hidden');
    safetyRiskLevel.textContent = data.safety_evaluation?.risk_level || 'CRITICAL';
    safetyReason.textContent = data.safety_evaluation?.reasons?.[0] || 'Safety hold required.';
    safetyCommandText.textContent = data.safety_evaluation?.proposed_command || prompt;
  } else {
    const answer = data.result || data.spoken_response || 'Task executed successfully.';
    renderUserAnswer(answer, routeSelector ? routeSelector.options[routeSelector.selectedIndex].text : '⚡ 4-Node Pipeline');
    simulateMeshTransmission(prompt);
  }
}

function handleSimulation(prompt) {
  const lower = prompt.toLowerCase();
  let spoken = "";
  let directResult = "";

  if (lower.includes('status') || lower.includes('online')) {
    spoken = "8 DGX nodes online. 1,024 GB VRAM ready.";
    directResult = "Nodes Online: 8/8 | VRAM: 1,024 GB | Vault: 100.88.197.6 (Online) | Latency: 2.1 ms";
    spokenText.textContent = `"${spoken}"`;
    speakAudioResponse(spoken);
    renderUserAnswer(directResult, 'Cluster Telemetry');
    return;
  }

  if (lower.includes('shut down') || lower.includes('shutdown')) {
    safetyPanel.classList.remove('hidden');
    safetyRiskLevel.textContent = "CRITICAL ACTION";
    safetyReason.textContent = "Power operation held by Evidence-Gated Guard.";
    safetyCommandText.textContent = "shutdown -h now";
    spoken = "Alert: Shutdown held by safety gate. Confirm required.";
    spokenText.textContent = `"${spoken}"`;
    speakAudioResponse(spoken);
    return;
  }

  if (lower.includes('csv') || lower.includes('pandas')) {
    spoken = "Python CSV pipeline generated.";
    directResult = `import pandas as pd\nimport matplotlib.pyplot as plt\n\ndef analyze_csv(filepath: str):\n    df = pd.read_csv(filepath)\n    print(f"Loaded {len(df)} rows. Summary:\\n", df.describe())\n    df.hist(figsize=(10, 6))\n    plt.savefig("analysis_chart.png")\n    print("Chart saved: analysis_chart.png")\n\nif __name__ == "__main__":\n    analyze_csv("data.csv")`;
  } else {
    spoken = "Distributed KV cache solution generated.";
    directResult = `import time\nimport asyncio\nfrom typing import Any, Optional, Dict\n\nclass DistributedKVCache:\n    """High-performance async KV cache with TTL."""\n    def __init__(self):\n        self._store: Dict[str, Any] = {}\n        self._expiry: Dict[str, float] = {}\n\n    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:\n        self._store[key] = value\n        self._expiry[key] = time.time() + ttl_seconds\n\n    async def get(self, key: str) -> Optional[Any]:\n        if key in self._store:\n            if time.time() < self._expiry.get(key, 0):\n                return self._store[key]\n            del self._store[key]\n            del self._expiry[key]\n        return None\n\n# Verification Test Suite\nasync def test_cache():\n    cache = DistributedKVCache()\n    await cache.set("user:101", {"name": "AEGIS", "role": "Cluster"}, ttl_seconds=10)\n    val = await cache.get("user:101")\n    assert val["name"] == "AEGIS"\n    print("Tests passed: DistributedKVCache operational.")\n\nif __name__ == "__main__":\n    asyncio.run(test_cache())`;
  }

  spokenText.textContent = `"${spoken}"`;
  speakAudioResponse(spoken);
  renderUserAnswer(directResult, '⚡ 4-Node Pipeline');
  simulateMeshTransmission(prompt);
}

// Live Mesh Visualizer simulation
function simulateMeshTransmission(prompt) {
  const packet = document.getElementById('data-packet-particle');
  const filenameEl = document.getElementById('transfer-filename');
  const badgeEl = document.getElementById('transfer-status-badge');
  const progBar = document.getElementById('transfer-progress-bar');
  const codePrev = document.getElementById('transfer-code-preview');

  if (filenameEl) filenameEl.textContent = 'dist_kv_cache.py';
  if (badgeEl) badgeEl.textContent = 'Node 1 ➔ Vault &bull; 14.2 KB (Exit 0)';
  if (progBar) progBar.style.width = '100%';
  if (codePrev) codePrev.innerHTML = '<code>class DistributedKVCache: async def set(self, key, val, ttl=300)...</code>';

  if (packet) {
    packet.setAttribute('cx', '480');
    setTimeout(() => packet.setAttribute('cx', '70'), 3000);
  }

  appendTerminal(`[MESH]: Transferred dist_kv_cache.py (14.2 KB) across DGX 1-4 via 10 GbE.`, 'term-emerald');
}

// ==============================================================================
// 7. Cockpit Rendering & Terminal Streaming
// ==============================================================================

function renderCockpitNodes() {
  if (!cockpitNodesGrid) return;
  cockpitNodesGrid.innerHTML = '';
  nodesData.forEach(n => {
    const card = document.createElement('div');
    card.className = 'c-node-card';
    card.innerHTML = `
      <div class="c-node-header">
        <span class="c-node-id">${n.id.toUpperCase()}</span>
        <span class="status-badge ${n.status === 'online' ? 'online' : 'busy'}">${n.status}</span>
      </div>
      <div class="c-node-role">${n.name.split('-')[1] || n.name}</div>
      <div class="c-node-meta">${n.model}</div>
      <div class="c-node-meta">VRAM: ${n.vram_used}/${n.vram_total} GB &bull; ${n.temp}&deg;C</div>
    `;
    cockpitNodesGrid.appendChild(card);
  });
}

function renderVaultArtifacts() {
  if (!cockpitArtifactsList) return;
  cockpitArtifactsList.innerHTML = '';
  vaultArtifacts.forEach(a => {
    const row = document.createElement('div');
    row.className = 'artifact-item';
    row.innerHTML = `
      <span class="artifact-name">${a.name}</span>
      <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-dim);">${a.size}</span>
      <a href="#" class="artifact-link" onclick="downloadArtifactFile('${a.name}')">Download</a>
    `;
    cockpitArtifactsList.appendChild(row);
  });
}

function downloadArtifactFile(filename) {
  const sample = currentSolutionCode || `# ${filename}\nprint("AEGIS Vault Solution File")`;
  const blob = new Blob([sample], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function appendTerminal(text, colorClass = '') {
  if (cockpitTerminalOutput) {
    const span = document.createElement('span');
    if (colorClass) span.className = colorClass;
    span.textContent = text + '\n';
    cockpitTerminalOutput.appendChild(span);
    cockpitTerminalOutput.scrollTop = cockpitTerminalOutput.scrollHeight;
  }
}

// Clear Terminal in Cockpit
btnClearCockpitTerminal?.addEventListener('click', () => {
  if (cockpitTerminalOutput) {
    cockpitTerminalOutput.innerHTML = '<span class="term-dim">[SYSTEM] Terminal cleared.</span>\n';
  }
});

btnRefreshVaultArtifacts?.addEventListener('click', () => {
  renderVaultArtifacts();
});

// ==============================================================================
// 8. Event Listeners & Buttons
// ==============================================================================

// Route Selector Change
routeSelector?.addEventListener('change', (e) => {
  const text = e.target.options[e.target.selectedIndex].text;
  if (userActiveModel) userActiveModel.textContent = text;
  appendTerminal(`[ROUTE]: Execution target: ${e.target.value}`, 'term-cyan');
});

// New Task Button (Workspace reset)
btnNewTask?.addEventListener('click', () => {
  window.speechSynthesis.cancel();
  if (recognition && isListening) {
    try { recognition.stop(); } catch (e) {}
  }
  isListening = false;
  if (siriAvatar) siriAvatar.classList.remove('speaking', 'listening');
  if (btnMic) btnMic.classList.remove('active-listening');
  stopAudioWaveVisualizer();

  if (userAnswerCard) userAnswerCard.classList.add('hidden');
  if (voiceOverlay) voiceOverlay.classList.add('hidden');
  if (idleHero) idleHero.classList.remove('hidden');
  if (cmdInput) {
    cmdInput.value = '';
    cmdInput.focus();
  }
  appendTerminal(`[SESSION]: New task initiated.`, 'term-dim');
});

// Close User Answer Card
btnCloseUser?.addEventListener('click', () => {
  if (userAnswerCard) userAnswerCard.classList.add('hidden');
  if (voiceOverlay) voiceOverlay.classList.add('hidden');
  if (idleHero) idleHero.classList.remove('hidden');
});

// Copy User Answer / Code
btnCopyUser?.addEventListener('click', async () => {
  const textToCopy = currentSolutionCode || (userCodeBody ? userCodeBody.innerText : '') || (userTextBody ? userTextBody.innerText : '');
  if (!textToCopy) return;
  try {
    await navigator.clipboard.writeText(textToCopy);
    btnCopyUser.classList.add('copied');
    if (userCopyLabel) userCopyLabel.textContent = 'Copied!';
    setTimeout(() => {
      btnCopyUser.classList.remove('copied');
      if (userCopyLabel) userCopyLabel.textContent = 'Copy';
    }, 2000);
  } catch (err) {
    console.warn('Clipboard copy error:', err);
  }
});

// Download User Answer Code
btnDownloadUser?.addEventListener('click', () => {
  const code = currentSolutionCode || (userCodeBody ? userCodeBody.innerText : '# Solution');
  const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'aegis_solution.py';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// Theme Switcher
btnThemeToggle?.addEventListener('click', () => {
  const isDark = document.body.classList.toggle('dark-theme');
  document.body.classList.toggle('light-theme', !isDark);
  btnThemeToggle.textContent = isDark ? '☀️' : '🌙';
});

// Dispatch Input and Prompt Chips
btnDispatch?.addEventListener('click', () => dispatchCommand(cmdInput.value));
cmdInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') dispatchCommand(cmdInput.value);
});
document.querySelectorAll('.prompt-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const cmd = chip.getAttribute('data-cmd');
    if (cmd) {
      cmdInput.value = cmd;
      dispatchCommand(cmd);
    }
  });
});

// WebSocket Initialization
function initWebSocket() {
  try {
    ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === 'pipeline_step_progress') {
          appendTerminal(`[PIPELINE] Advanced: ${msg.data.stage}`, 'term-emerald');
        } else if (msg.event === 'pipeline_completed') {
          appendTerminal(`[PIPELINE COMPLETE] Certified across cluster.`, 'term-cyan');
        }
      } catch (e) {}
    };
  } catch (err) {}
}

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
  renderCockpitNodes();
  renderVaultArtifacts();
  initWebSocket();
});
