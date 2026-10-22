"""AEGIS Evidence-Gated Safety & Permission Engine.
Guards compute nodes against catastrophic commands, unverified shutdowns, and unsafe script execution.
"""
import re
from typing import List, Tuple
from aegis_core.models import SafetyEvaluation

class SafetyGuard:
    def __init__(self, high_risk_patterns: List[str] = None):
        self.high_risk_patterns = high_risk_patterns or [
            r"rm\s+-rf\s+[/~]",
            r"rm\s+-rf\s+\*",
            r"\b(shutdown|reboot|poweroff|halt|init\s+0)\b",
            r"\bmkfs\b",
            r"\bdd\s+if=.*\bof=/dev/",
            r"\b(iptables\s+-F|ufw\s+disable)\b",
            r"\bkill\s+-9\s+1\b",
            r">>\s*/dev/sd[a-z]",
            r"\bchmod\s+-R\s+777\s+/",
            r"\bchown\s+-R\s+.*\s+/",
        ]
        
        self.medium_risk_patterns = [
            r"\bsystemctl\s+(stop|restart|disable)\b",
            r"\bpkill\b",
            r"\bkillall\b",
            r"\bapt\s+(remove|purge)\b",
            r"\bpip\s+uninstall\b",
            r"\bgit\s+reset\s+--hard\b",
            r"\bgit\s+clean\s+-fdx\b"
        ]

    def evaluate_command(self, command: str) -> SafetyEvaluation:
        """Inspects shell commands, assigning risk levels and confirmation requirements."""
        if not command or not command.strip():
            return SafetyEvaluation(
                is_safe=True,
                risk_level="LOW",
                requires_confirmation=False,
                reasons=["Empty or no-op command."],
                proposed_command=command
            )

        cmd_lower = command.lower().strip()
        reasons = []
        risk_level = "LOW"
        requires_confirmation = False

        # 1. Critical pattern checks
        for pat in self.high_risk_patterns:
            if re.search(pat, cmd_lower):
                reasons.append(f"Command matches high-risk destructive pattern: `{pat}`")
                risk_level = "CRITICAL"
                requires_confirmation = True

        # 2. Medium pattern checks
        if risk_level != "CRITICAL":
            for pat in self.medium_risk_patterns:
                if re.search(pat, cmd_lower):
                    reasons.append(f"Command performs state mutation/service interruption: `{pat}`")
                    risk_level = "MEDIUM"
                    requires_confirmation = True

        # 3. Path checking for filesystem boundary containment
        if "rm " in cmd_lower and not requires_confirmation:
            if re.search(r"\brm\s+-[a-zA-Z]*f", cmd_lower):
                reasons.append("Force removal flag (-f) detected.")
                risk_level = "MEDIUM"
                requires_confirmation = True

        is_safe = (risk_level == "LOW")
        return SafetyEvaluation(
            is_safe=is_safe,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            reasons=reasons if reasons else ["Command verified safe within execution sandbox."],
            proposed_command=command
        )

    def format_warning_speech(self, eval_result: SafetyEvaluation, lang: str = "hi-en") -> str:
        """Generates clear, voice-friendly alert message in English or Hindi/Hinglish."""
        if not eval_result.requires_confirmation:
            return ""

        if lang in ["hi", "hi-en"]:
            return (
                f"Savdhaan! Yeh command high risk category me hai: '{eval_result.proposed_command}'. "
                f"Kripya aage badhne ke liye 'AEGIS, confirm' bolein ya dashboard par approve karein."
            )
        else:
            return (
                f"Attention. This command requires safety authorization: '{eval_result.proposed_command}'. "
                f"Please say 'AEGIS, confirm' or authorize from the control dashboard."
            )
