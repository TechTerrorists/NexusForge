"""PromptInjectionGuardMiddleware — heuristic risk scoring for prompt injection attempts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

from packages.middleware.pipeline import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Risk taxonomy                                                                 #
# --------------------------------------------------------------------------- #

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RiskMatch:
    """A single risk signal found in text."""
    pattern: str
    level: RiskLevel
    description: str


@dataclass
class RiskScore:
    """Aggregated risk assessment for a piece of text."""
    level: RiskLevel
    matches: list[RiskMatch]

    @property
    def is_high(self) -> bool:
        return self.level == RiskLevel.HIGH

    @property
    def is_medium_or_above(self) -> bool:
        return self.level in (RiskLevel.MEDIUM, RiskLevel.HIGH)


# --------------------------------------------------------------------------- #
# Pattern registry                                                             #
# --------------------------------------------------------------------------- #

HIGH_RISK_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("instruction_override", re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I), "Instruction override"),
    ("role_takeover", re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I), "Role takeover attempt"),
    ("role_takeover_2", re.compile(r"act\s+as\s+if\s+you\s+(were|are|had)", re.I), "Role takeover attempt"),
    ("role_takeover_3", re.compile(r"pretend\s+(you\s+are|to\s+be|you're)", re.I), "Pretend identity"),
    ("credential_exfil", re.compile(r"(send|post|transmit|exfiltrate)\s+(the\s+)?(api[_\s-]?key|secret|token|password|credential)", re.I), "Credential exfiltration"),
    ("system_override", re.compile(r"(new|override|replace)\s+system\s+(prompt|instructions?)", re.I), "System prompt override"),
    ("jailbreak_dan", re.compile(r"\bDAN\b.*\bmode\b|\bdo\s+anything\s+now\b", re.I), "DAN jailbreak"),
    ("jailbreak_generic", re.compile(r"jailbreak|jail\s*break", re.I), "Jailbreak attempt"),
    ("hidden_command", re.compile(r"<\|(im_start|im_end|system|endoftext)\|>", re.I), "Hidden system delimiter"),
    ("base64_payload", re.compile(r"(decode|interpret|execute)\s+(this\s+)?base64", re.I), "Encoded payload"),
    ("data_exfil_url", re.compile(r"(fetch|send|POST)\s+(the\s+)?(data|content|files?)\s+to\s+(https?://|ftp://)", re.I), "Data exfiltration URL"),
    ("delimiter_injection", re.compile(r"(###|---)\s*(system|assistant|user)\s*(###|---)", re.I), "Delimiter injection"),
    ("role_marker", re.compile(r"\[(INST|SYS|SYSTEM)\]", re.I), "Role marker injection"),
]

MEDIUM_RISK_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("delimiter_injection_soft", re.compile(r"(?:^|\n)#{1,3}\s*system\s*:", re.I), "Potential system header injection"),
    ("encoded_escape", re.compile(r"\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}", re.I), "Encoded character escape"),
    ("template_injection", re.compile(r"\{\{.*\}\}|\$\{.*\}", re.I), "Template variable injection"),
    ("instruction_continuation", re.compile(r"(?:and|also|additionally)\s+ignore\s+(the\s+)?above", re.I), "Instruction continuation"),
    ("fake_assistant", re.compile(r"(?:assistant|ai)\s*:\s*(?:I\s+will|Let\s+me|Sure)", re.I), "Fake assistant response"),
    ("system_leak_provoke", re.compile(r"(repeat|output|print|show)\s+(your\s+)?(system\s*prompt|instructions?|rules?)", re.I), "System prompt leak attempt"),
]


# --------------------------------------------------------------------------- #
# Scanner                                                                       #
# --------------------------------------------------------------------------- #

def _scan_text(text: str) -> RiskScore:
    """Evaluate *text* against all known injection patterns."""
    matches: list[RiskMatch] = []

    for name, pattern, desc in HIGH_RISK_PATTERNS:
        if pattern.search(text):
            matches.append(RiskMatch(pattern=name, level=RiskLevel.HIGH, description=desc))

    for name, pattern, desc in MEDIUM_RISK_PATTERNS:
        if pattern.search(text):
            matches.append(RiskMatch(pattern=name, level=RiskLevel.MEDIUM, description=desc))

    if any(m.level == RiskLevel.HIGH for m in matches):
        level = RiskLevel.HIGH
    elif any(m.level == RiskLevel.MEDIUM for m in matches):
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    return RiskScore(level=level, matches=matches)


# --------------------------------------------------------------------------- #
# Middleware                                                                    #
# --------------------------------------------------------------------------- #

class PromptInjectionGuardMiddleware(Middleware):
    """Scans user messages for prompt-injection signals before the model call.

    Behaviour:
        HIGH risk  → cancels the pipeline with an error.
        MEDIUM risk → logs a warning but lets execution continue.
    """

    name = "prompt_guard"

    def __init__(self, block_high: bool = True, log_medium: bool = True) -> None:
        self.block_high = block_high
        self.log_medium = log_medium

    def scan(self, text: str) -> RiskScore:
        """Public scan API for standalone use."""
        return _scan_text(text)

    # ---- middleware hooks --------------------------------------------------- #

    async def before_agent(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """Scan the most recent user message in the state."""
        messages = ctx.state.get("messages", [])
        user_texts: list[str] = []

        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            elif hasattr(msg, "type"):
                role = getattr(msg, "type", "")
                content = getattr(msg, "content", "")
            else:
                continue

            if role in ("user", "human") and isinstance(content, str):
                user_texts.append(content)

        for text in user_texts:
            score = _scan_text(text)

            if score.is_high and self.block_high:
                ctx.cancelled = True
                ctx.cancel_reason = (
                    f"Prompt injection detected (HIGH risk): "
                    f"{[m.description for m in score.matches if m.level == RiskLevel.HIGH]}"
                )
                logger.warning("PromptGuard: %s", ctx.cancel_reason)
                return ctx

            if score.is_medium_or_above and self.log_medium:
                logger.warning(
                    "PromptGuard: MEDIUM risk in user message — %s",
                    [m.description for m in score.matches],
                )

        return ctx
