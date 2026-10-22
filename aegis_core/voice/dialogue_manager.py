"""AEGIS Multilingual Voice Dialogue Manager.
Parses natural spoken commands in English, Hindi, and Hinglish, mapping them to actionable system intents.
"""
import re
from typing import Dict, Any, Optional

class DialogueManager:
    def __init__(self):
        # Intent patterns matching English and Hindi/Hinglish
        self.intent_patterns = [
            ("CLUSTER_STATUS", [
                r"\b(?:status|online|active)\b.*?\b(?:nodes?|dgx|cluster|machines?)\b",
                r"\b(?:nodes?|dgx|cluster|machines?)\b.*?\b(?:status|online|active)\b",
                r"\b(?:tell me which dgx nodes are online|kaun kaun se|kitne nodes|sabhi nodes)\b",
                r"\b(?:cluster status|node status|lab status|show nodes)\b"
            ]),
            ("CODE_TASK", [
                r"\b(create|build|make|banao|shuru karo|generate|write)\s*(a|an)?\s*(python|code|project|script|analysis|program)\b",
                r"\b(coding agent|coding shuru|code analysis)\b"
            ]),
            ("REVIEW_TASK", [
                r"\b(ask|tell|bolo|kaho)?\s*(another|reviewer)?\s*(node|agent)?\s*(to)?\s*(review|verify|check|test|inspect)\b",
                r"\b(code review|review the code|run the tests|tests chalao)\b"
            ]),
            ("FIX_ERROR", [
                r"\b(explain|fix|the error|kya error hai|error theek karo|attempt a safe fix)\b",
                r"\b(explain the error on node|troubleshoot node)\b"
            ]),
            ("SHOW_RESULTS", [
                r"\b(read me|show me|results|dikhao|batao|generated files|artifacts|final result)\b"
            ]),
            ("CONFIRM_ACTION", [
                r"\b(confirm|approve|proceed|yes|haan|theek hai|aage badho|manzoor|start now)\b"
            ]),
            ("SHUTDOWN_NODE", [
                r"\b(safely shut down|turn off|band karo|shutdown|poweroff)\s*(node\s*\d+|dgx\s*\d+)?\b"
            ]),
            ("EXPLICIT_NODE_TARGET", [
                r"\b(node\s*(\d+)|dgx\s*(\d+))\b"
            ])
        ]

    def parse(self, text: str) -> Dict[str, Any]:
        """Classifies speech input and extracts parameters (target node, prompt, action)."""
        raw = text.strip()
        cleaned = raw.lower()
        
        # Remove wake word if present in transcribed audio
        cleaned = re.sub(r"^(hey\s+)?aegis[,\s]*", "", cleaned).strip()

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

        # Detect language cues
        is_hindi = any(w in cleaned for w in ["hai", "hain", "karo", "batao", "dikhao", "banao", "chalao", "shuru", "kaun", "kya", "sab"])
        lang = "hi-en" if is_hindi else "en"

        return {
            "intent": matched_intent,
            "raw_text": raw,
            "cleaned_prompt": cleaned,
            "target_node": target_node,
            "language": lang
        }

    def generate_response_text(self, intent: str, context: Dict[str, Any], lang: str = "hi-en") -> str:
        """Generates conversational spoken responses in English or Hindi/Hinglish."""
        if intent == "CLUSTER_STATUS":
            active_count = context.get("online_nodes", 0)
            total = context.get("total_nodes", 8)
            if lang in ["hi", "hi-en"]:
                return f"Filhaal {active_count} out of {total} DGX nodes online aur ready hain. Terminals par live activity monitor ho rahi hai."
            return f"Currently, {active_count} of {total} DGX nodes are active and operating normally."

        elif intent == "CODE_TASK":
            node_name = context.get("node_name", "DGX Node 1")
            if lang in ["hi", "hi-en"]:
                return f"Samajh gaya. {node_name} ko coding task assign kar diya hai. Physical screen par terminal open ho chuka hai."
            return f"Task accepted. Routed to {node_name}. Live terminal session is now running on its display."

        elif intent == "REVIEW_TASK":
            rev_node = context.get("reviewer_node", "DGX Node 2")
            if lang in ["hi", "hi-en"]:
                return f"Result ko {rev_node} ke paas review aur automated testing ke liye forward kar diya hai."
            return f"Artifacts forwarded to {rev_node} for code review and test suite execution."

        elif intent == "CONFIRM_ACTION":
            if lang in ["hi", "hi-en"]:
                return "Command authorized. Execution shuru kar rahe hain."
            return "Action authorized. Proceeding with execution."

        elif intent == "SHUTDOWN_NODE":
            target = context.get("target_node", "the requested node")
            if lang in ["hi", "hi-en"]:
                return f"{target} ko safely terminate karne ki command prepare kar di hai. Evidence verify ho chuka hai."
            return f"Safety check complete. Safely shutting down {target}."

        else:
            if lang in ["hi", "hi-en"]:
                return "Aapka command assign kar diya gaya hai. Real-time updates physical screens par visible hain."
            return "Command received and scheduled across the DGX cluster."
