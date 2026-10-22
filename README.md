# AEGIS: Adaptive Evidence-Gated Intelligence System

Voice-first control and orchestration layer for an AI lab containing **8 independent NVIDIA DGX Spark machines**, a central **Raspberry Pi 8GB coordinator**, and a shared **i7-14700 artifact storage server**.

---

## 🏛️ System Architecture

```
                 🎙️ Natural Voice Input (Hindi / Hinglish / English)
                                   │
                                   ▼
          ┌─────────────────────────────────────────────────┐
          │     Raspberry Pi 8GB — AEGIS Core Orchestrator  │
          │   (Wake-word, Intent Parser, Router, Safety)    │
          │               Port: 9000 (REST / WS)            │
          └────────────────────────┬────────────────────────┘
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         │                                                   │
         ▼                                                   ▼
┌──────────────────────────────┐           ┌──────────────────────────────────────┐
│  8x NVIDIA DGX Spark Nodes   │           │   i7-14700 PC — Shared Storage Vault │
│  (dgx-node-1 to dgx-node-8)  │           │     (This Machine: LABG418PC12)      │
│  - Local LLM (Ollama/vLLM)   │           │   - Artifact Storage & Log Vault     │
│  - Persistent Terminal (pty) │           │   - AEGIS Mission Control Dashboard  │
│  - Physical Desktop HUD      │           │   - Tailscale: labg418pc12 (9080)    │
└──────────────────────────────┘           └──────────────────────────────────────┘
```

---

## 🚀 Quick Start (Running on this i7-14700 PC)

### 1. Launch All AEGIS Services
To launch both the Core Orchestrator (port 9000) and the Mission Control Dashboard & Storage Server (port 9080) simultaneously:
```powershell
python run_aegis.py --all
```

- **Mission Control Web UI**: Open your browser at [http://localhost:9080](http://localhost:9080)
- **Coordinator REST & WebSocket API**: [http://localhost:9000](http://localhost:9000)

### 2. Standalone Modes
- Run only the Central Coordinator (on Raspberry Pi or locally):
  ```bash
  python run_aegis.py --core --port 9000
  ```
- Run only the Shared Storage & Mission Control Server:
  ```bash
  python run_aegis.py --server --port 9080
  ```

---

## 🖥️ Deploying a DGX Spark Node Agent

On any of the 8 Ubuntu DGX machines, navigate to the `aegis_node` directory and run:

```bash
# Automated setup (installs virtualenv, dependencies & systemd service)
chmod +x setup_node.sh
./setup_node.sh dgx-node-1 http://100.106.207.27:9000 http://100.88.197.6:9080
```

To run manually with live desktop overlay HUD on physical screen `:0`:
```bash
python -m aegis_node.agent_service --id dgx-node-1 --coordinator http://100.106.207.27:9000 --artifact-server http://100.88.197.6:9080 --hud
```

---

## 🎙️ Sample Natural Voice Commands Supported

AEGIS parses speech in English, Hindi, and Hinglish:

| Voice Command | Action / Route |
| :--- | :--- |
| *"AEGIS, tell me which DGX nodes are online and what each is doing."* | Queries cluster status, counts active nodes, speaks summary |
| *"Sabhi DGX nodes ka status batao."* | Hindi cluster status reporting |
| *"AEGIS, create a Python project that analyses a CSV file."* | Routes task to **DGX Spark 03 (Data Science)** |
| *"Ask Node 2 to review the code and run the tests."* | Handoff to **DGX Spark 02 (Reviewer/Verifier)** |
| *"Safely shut down Node 5."* | **Evidence-Gated Safety Hold**: Requires voice confirmation or dashboard click |

---

## 🛡️ Evidence-Gated Safety

High-impact actions (such as `rm -rf`, `shutdown`, `reboot`, `systemctl stop`) are automatically evaluated by the `SafetyGuard`. Dangerous commands are flagged as `CRITICAL` or `MEDIUM` risk and placed into an `awaiting_approval` state until explicit authorization is given via speech (`"AEGIS, confirm"`) or the interactive dashboard modal.

---

## 🧪 Running Unit Tests

```powershell
python -m unittest tests/test_aegis.py
```
All unit tests verify:
- Destructive pattern isolation in `SafetyGuard`
- English and Hindi/Hinglish intent classification in `DialogueManager`
- Node inventory tracking and task lifecycle in `StateManager`
- Intelligent node matching and multi-node handoff in `Orchestrator`
