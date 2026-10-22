"""AEGIS Router Custom Dataset Generator.
Generates thousands of synthetic multilingual (Hindi, Hinglish, English) lab training samples
for training the custom Raspberry Pi edge intelligence and routing model from scratch.
"""
import json
import random
from typing import List, Dict

SYSTEM_PROMPT = (
    "You are AEGIS-Router, a low-latency edge AI model running on Raspberry Pi. "
    "Your job is to parse voice input from lab engineers in English, Hindi, or Hinglish, "
    "and output a structured JSON routing decision for the 8x NVIDIA DGX Spark cluster."
)

NODES = {
    "dgx-node-1": {"role": "Coder Model", "actions": ["code_generation", "debug", "refactor", "api_development"]},
    "dgx-node-2": {"role": "Reviewer & QA", "actions": ["code_review", "unit_test_generation", "logic_check"]},
    "dgx-node-3": {"role": "Vision Model", "actions": ["ocr", "diagram_analysis", "screenshot_inspection", "video_scan"]},
    "dgx-node-4": {"role": "Writer & Reasoner", "actions": ["deep_reasoning", "whitepaper", "research_notes", "math_proof"]},
    "dgx-node-5": {"role": "Security Auditor", "actions": ["cve_scan", "vulnerability_audit", "jailbreak_check", "exploit_analysis"]},
    "dgx-node-6": {"role": "Image Gen Studio", "actions": ["text_to_image", "diagram_render", "ui_mockup"]},
    "dgx-node-7": {"role": "Comms & Git Ops", "actions": ["git_commit", "github_pr", "system_triage", "bash_script"]},
    "dgx-node-8": {"role": "Doc Synthesizer", "actions": ["pdf_generation", "docx_report", "latex_synthesis", "csv_table"]},
    "pi_hub": {"role": "Local Pi Hub", "actions": ["cluster_status", "telemetry_summary", "audio_volume", "greeting"]}
}

TEMPLATES = [
    # DGX 1 - Coder
    ("AEGIS, create a Python project that analyses {topic} data", "dgx-node-1", "code_generation", False, True, "LOW"),
    ("Node 1 pe ek script banao jo {topic} handle kare", "dgx-node-1", "code_generation", False, True, "LOW"),
    ("Write a fast C++ / CUDA implementation for {topic}", "dgx-node-1", "code_generation", False, True, "LOW"),
    ("Bhai ek REST API bana do FastAPI me for {topic}", "dgx-node-1", "code_generation", False, True, "LOW"),
    ("Debug the memory leak in the {topic} service", "dgx-node-1", "debug", False, False, "LOW"),

    # DGX 2 - Reviewer & QA
    ("Ask Node 2 to review the code and run test suite", "dgx-node-2", "code_review", False, True, "LOW"),
    ("Node 2 ko bolo code check kare aur pytest run kare", "dgx-node-2", "unit_test_generation", False, True, "LOW"),
    ("Audit this pull request for logic errors and edge cases", "dgx-node-2", "code_review", False, False, "LOW"),

    # DGX 3 - Vision
    ("Explain the architecture diagram from this image", "dgx-node-3", "diagram_analysis", False, True, "LOW"),
    ("Is screenshot me jo error message hai use read karo aur samjhao", "dgx-node-3", "ocr", False, False, "LOW"),
    ("Scan this document page and extract all text and tables", "dgx-node-3", "ocr", False, True, "LOW"),

    # DGX 4 - Writer & Reasoner
    ("Write a comprehensive research report on {topic}", "dgx-node-4", "research_notes", False, True, "LOW"),
    ("Is algorithm ka mathematical proof explain karo step by step", "dgx-node-4", "math_proof", False, False, "LOW"),
    ("Draft a detailed technical architecture whitepaper for {topic}", "dgx-node-4", "whitepaper", False, True, "LOW"),

    # DGX 5 - Security
    ("Run a security audit on our authentication endpoint", "dgx-node-5", "vulnerability_audit", False, False, "LOW"),
    ("Check dependencies for known CVEs and security holes", "dgx-node-5", "cve_scan", False, True, "LOW"),
    ("Safely shut down Node 5", "dgx-node-5", "shutdown_node", True, False, "CRITICAL"),
    ("Systemctl stop firewalld on node 5", "dgx-node-5", "stop_service", True, False, "HIGH"),

    # DGX 6 - Image Gen
    ("Generate a modern UI mockup for a cloud dashboard", "dgx-node-6", "ui_mockup", False, True, "LOW"),
    ("Hunyuan se ek futuristic AI lab ka photorealistic visual render karo", "dgx-node-6", "text_to_image", False, True, "LOW"),
    ("FLUX.1 se high resolution architecture poster banao", "dgx-node-6", "diagram_render", False, True, "LOW"),

    # DGX 7 - Comms & Git
    ("Commit current changes and push to origin main on GitHub", "dgx-node-7", "git_commit", False, False, "MEDIUM"),
    ("Node 7 ko bolo new git branch banaye aur PR open kare", "dgx-node-7", "github_pr", False, False, "LOW"),

    # DGX 8 - Doc Synthesizer
    ("Generate a formal PDF report summarizing today's experiment", "dgx-node-8", "pdf_generation", False, True, "LOW"),
    ("Ek clean Word document .docx banao meeting notes ka", "dgx-node-8", "docx_report", False, True, "LOW"),
    ("Export this data to a formatted CSV spreadsheet", "dgx-node-8", "csv_table", False, True, "LOW"),

    # Pi Hub - Local
    ("AEGIS, tell me which DGX nodes are online and what each is doing", "pi_hub", "cluster_status", False, False, "LOW"),
    ("Sabhi DGX nodes ka status batao", "pi_hub", "cluster_status", False, False, "LOW"),
    ("Volume thoda badha do headphone me", "pi_hub", "audio_volume", False, False, "LOW"),
    ("Hey AEGIS, how are you today?", "pi_hub", "greeting", False, False, "LOW")
]

TOPICS = [
    "time-series financial", "medical imaging", "genomic sequencing", "deep learning inference",
    "network packet capture", "distributed cache", "PostgreSQL database", "microservices telemetry",
    "autonomous robot sensors", "satellite weather", "e-commerce user logs", "voice biometric"
]

def generate_samples(count: int = 1500) -> List[Dict[str, str]]:
    dataset = []
    for _ in range(count):
        tmpl, node, action, requires_conf, drive_sync, risk = random.choice(TEMPLATES)
        topic = random.choice(TOPICS)
        user_input = tmpl.format(topic=topic)

        output_dict = {
            "target_node": node,
            "action": action,
            "requires_confirmation": requires_conf,
            "drive_sync_required": drive_sync,
            "risk_level": risk,
            "spoken_acknowledgment": f"Routing to {NODES[node]['role']}." if node != "pi_hub" else "Checking cluster status."
        }

        dataset.append({
            "instruction": SYSTEM_PROMPT,
            "input": user_input,
            "output": json.dumps(output_dict, separators=(",", ":"))
        })

    return dataset

if __name__ == "__main__":
    data = generate_samples(2000)
    output_path = "aegis_router_training/router_training_data.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Generated {len(data)} training samples at: {output_path}")
