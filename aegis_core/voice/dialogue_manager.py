"""AEGIS Multilingual Voice Dialogue Manager.
Parses natural spoken commands in English, Hindi, and Hinglish, mapping them to actionable cluster intents.
Generates warm, intelligent spoken responses tailored to the 4 DGX flagship nodes.
"""
import re
from typing import Dict, Any, Optional

class DialogueManager:
    def __init__(self):
        # Comprehensive intent patterns matching English, Hindi, and colloquial Hinglish
        self.intent_patterns = [
            ("PIPELINE_TASK", [
                r"\b(?:4[-\s]?node|four[-\s]?node|full[-\s]?cluster|autonomous|complete|distributed)\s*(?:pipeline|workflow|run|handoff|chalao|execute)\b",
                r"\b(?:pipeline\s*(?:chalao|run|execute|shuru|start))\b",
                r"\b(?:kv[-\s]?cache|cache\s*with\s*ttl|distributed\s*cache)\b",
                r"\b(?:node\s*1\s*(?:se|to|se\s*lekar)\s*node\s*4)\b"
            ]),
            ("CLUSTER_STATUS", [
                r"\b(?:status|online|active|health|kaun|kitne|haal|sab)\b.*?\b(?:nodes?|dgx|cluster|machines?|servers?|gpus?)\b",
                r"\b(?:nodes?|dgx|cluster|machines?|servers?|gpus?)\b.*?\b(?:status|online|active|health|haal|check)\b",
                r"\b(?:tell me which dgx nodes are online|kaun kaun se|kitne nodes|sabhi nodes|kya chal raha hai)\b",
                r"\b(?:cluster status|node status|lab status|show nodes|gpu status|vram status)\b",
                r"\b(?:sabhi dgx nodes ka status batao|status batao|kya status hai)\b"
            ]),
            ("ARCHITECTURE_TASK", [
                r"\b(?:architecture|system\s*design|dataflow|diagram|visual|spec|flowchart)\b",
                r"\b(?:node\s*3|dgx\s*3)\b.*?\b(?:architecture|design|diagram|vision|spec)\b",
                r"\b(?:architecture\s*banao|design\s*explain|system\s*architecture)\b"
            ]),
            ("SECURITY_AUDIT", [
                r"\b(?:security|audit|harden|vulnerability|cve|bounds|memory\s*safety|safety\s*gate)\b",
                r"\b(?:node\s*4|dgx\s*4)\b.*?\b(?:security|audit|verify|check|harden)\b",
                r"\b(?:security\s*check\s*karo|audit\s*karo|code\s*harden\s*karo)\b"
            ]),
            ("CODE_TASK", [
                r"\b(?:create|build|make|banao|shuru\s*karo|generate|write|likho|develop)\s*(?:a|an)?\s*(?:python|code|project|script|analysis|program|app|api|service)\b",
                r"\b(?:coding\s*agent|coding\s*shuru|code\s*analysis|python\s*script|csv\s*project|data\s*pipeline)\b",
                r"\b(?:ek\s*(?:python|script|code|program)\s*(?:banao|likho|create\s*karo))\b"
            ]),
            ("REVIEW_TASK", [
                r"\b(?:ask|tell|bolo|kaho)?\s*(?:another|reviewer)?\s*(?:node|agent)?\s*(?:to)?\s*(?:review|verify|check|test|inspect|pytest)\b",
                r"\b(?:code\s*review|review\s*the\s*code|run\s*(?:the\s*)?tests|tests\s*chalao|pytest\s*run\s*karo)\b",
                r"\b(?:test\s*suite\s*generate|verification\s*karo)\b"
            ]),
            ("FIX_ERROR", [
                r"\b(?:explain|fix|the\s*error|kya\s*error\s*hai|error\s*theek\s*karo|attempt\s*a\s*safe\s*fix|bug\s*fix)\b",
                r"\b(?:explain\s*the\s*error\s*on\s*node|troubleshoot\s*node|galti\s*sudharo)\b"
            ]),
            ("SHOW_RESULTS", [
                r"\b(?:read\s*me|show\s*me|results?|dikhao|batao|generated\s*files|artifacts|final\s*result|files\s*kahan\s*hai)\b"
            ]),
            ("CONFIRM_ACTION", [
                r"\b(?:confirm|approve|proceed|yes|haan|theek\s*hai|aage\s*badho|manzoor|start\s*now|authorize)\b"
            ]),
            ("SHUTDOWN_NODE", [
                r"\b(?:safely\s*shut\s*down|turn\s*off|band\s*karo|shutdown|poweroff)\s*(?:node\s*\d+|dgx\s*\d+)?\b"
            ]),
            ("EXPLICIT_NODE_TARGET", [
                r"\b(?:node\s*([1-8])|dgx\s*([1-8]))\b"
            ])
        ]

    def parse(self, text: str) -> Dict[str, Any]:
        """Classifies speech input and extracts parameters (target node, prompt, action)."""
        raw = text.strip()
        cleaned = raw.lower()

        # Strip standard wake-words and salutations
        cleaned = re.sub(r"^(?:hey\s+|ok\s+|suno\s+|namaste\s+)?aegis[,\s]*", "", cleaned).strip()

        matched_intent = "GENERAL_TASK"
        target_node = None

        # Check explicit node references (e.g., "Node 3", "DGX 2")
        node_match = re.search(r"\b(?:node|dgx)\s*([1-8])\b", cleaned)
        if node_match:
            target_node = f"dgx-node-{node_match.group(1)}"

        # Match against intents
        for intent, patterns in self.intent_patterns:
            for pat in patterns:
                if re.search(pat, cleaned):
                    matched_intent = intent
                    break
            if matched_intent != "GENERAL_TASK":
                break

        # If it's a pipeline task, target is autonomous pipeline across nodes
        if matched_intent == "PIPELINE_TASK":
            target_node = target_node or "dgx-node-1"

        # Detect language cues (Hindi / Hinglish vs English)
        is_hindi = any(w in cleaned for w in [
            "hai", "hain", "karo", "batao", "dikhao", "banao", "chalao", "shuru",
            "kaun", "kya", "sab", "sabhi", "theek", "haan", "kaam", "chahiye", "kar", "do"
        ])
        lang = "hi-en" if is_hindi else "en"

        return {
            "intent": matched_intent,
            "raw_text": raw,
            "cleaned_prompt": cleaned,
            "target_node": target_node,
            "language": lang
        }

    def generate_response_text(self, intent: str, context: Dict[str, Any], lang: str = "hi-en") -> str:
        """Generates strictly concise, zero-filler responses in English or Hindi."""
        if intent == "PIPELINE_TASK":
            if lang in ["hi", "hi-en"]:
                return "Pipeline active: Node 1 se Node 4 sequential handoff shuru."
            return "4-Node pipeline active: Node 1 to Node 4."

        elif intent == "CLUSTER_STATUS":
            active_count = context.get("online_nodes", 8)
            total = context.get("total_nodes", 8)
            if lang in ["hi", "hi-en"]:
                return f"{active_count} DGX nodes online. 1,024 GB VRAM ready."
            return f"{active_count}/{total} DGX nodes online. 1,024 GB VRAM ready."

        elif intent == "CODE_TASK":
            node_name = context.get("node_name", "DGX Spark 01")
            if lang in ["hi", "hi-en"]:
                return f"{node_name} par code generation running."
            return f"{node_name} synthesizing code."

        elif intent == "REVIEW_TASK":
            rev_node = context.get("reviewer_node", "DGX Spark 02")
            if lang in ["hi", "hi-en"]:
                return f"{rev_node} par QA tests running."
            return f"{rev_node} executing QA test suite."

        elif intent == "ARCHITECTURE_TASK":
            if lang in ["hi", "hi-en"]:
                return "DGX-3 architecture design generate kar raha hai."
            return "DGX-3 generating architecture spec."

        elif intent == "SECURITY_AUDIT":
            if lang in ["hi", "hi-en"]:
                return "DGX-4 security audit execute kar raha hai."
            return "DGX-4 auditing security boundaries."

        elif intent == "CONFIRM_ACTION":
            if lang in ["hi", "hi-en"]:
                return "Action authorized. Executing."
            return "Action authorized. Executing."

        elif intent == "SHUTDOWN_NODE":
            target = context.get("target_node", "Node")
            if lang in ["hi", "hi-en"]:
                return f"Alert: {target} shutdown held by safety gate. Confirm required."
            return f"Hold: {target} shutdown requires authorization."

        else:
            if lang in ["hi", "hi-en"]:
                return "Task assigned. Executing."
            return "Task assigned. Executing."
