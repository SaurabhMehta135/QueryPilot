"""
app/guardrails/injection.py - Untrusted data wrapping and prompt injection defenses.
Ensures all database rows, tool outputs, schemas, and user-derived database strings
are safely escaped and wrapped in <untrusted_data> blocks before entering any LLM prompt.
"""

import json
import re
from typing import Any, Dict, Optional, Tuple


UNTRUSTED_OPEN = "<untrusted_data>"
UNTRUSTED_CLOSE = "</untrusted_data>"

DESTRUCTIVE_PATTERNS = [
    r"\bDROP\s+(?:TABLE|VIEW|INDEX|TRIGGER|DATABASE)\b",
    r"\bDELETE\s+(?:FROM|\*)\b",
    r"\bUPDATE\b\s+[\w\.\"\`\']+\s+\bSET\b",
    r"\bINSERT\s+INTO\b",
    r"\bALTER\s+TABLE\b",
    r"\bTRUNCATE\b",
    r"\bPRAGMA\b",
    r"\bATTACH\s+(?:DATABASE)?\b",
    r"\bsqlite_master\b",
    r"\bsqlite_schema\b",
]

PLAIN_ENGLISH_DESTRUCTIVE = [
    r"\bdelete\s+all\b",
    r"\bdrop\s+the\b",
    r"\bdrop\s+table\b",
    r"\bwipe\s+(?:out\s+)?(?:the\s+)?(?:table|database|records|all|orders|customers)\b",
    r"\bclear\s+(?:the\s+)?(?:table|database)\b",
    r"\btruncate\s+(?:the\s+)?table\b",
    r"\bpurge\s+(?:the\s+)?(?:table|database|all|records|orders|customers)\b",
    r"\bremove\s+all\s+(?:records|rows|data|customers|orders)\b",
    r"\bremove\s+every\b",
    r"\bupdate\s+all\b",
    r"\bmodify\s+all\b",
    r"\bset\s+all\b",
]


def escape_untrusted_delimiters(text: str) -> str:
    """
    Neutralizes any attempt to break out of the <untrusted_data> block
    by escaping all '<' and '>' characters into HTML entities &lt; and &gt;.
    """
    if not isinstance(text, str):
        text = str(text)

    # Neutralize common prompt injection wrapper attempts (<SYSTEM>, etc.)
    text = re.sub(r"<\s*/?\s*(?:system|instruction|override|admin)\s*>", "[ESCAPED_TAG]", text, flags=re.IGNORECASE)

    # Escape all '<' and '>' characters
    text = text.replace("<", "&lt;").replace(">", "&gt;")

    return text


def wrap_untrusted_data(content: Any, label: Optional[str] = None) -> str:
    """
    Standard wrapper used by ALL agents to encapsulate database rows,
    table schemas, sample values, diagnostic error strings, and previous SQL.
    No agent may inject raw database content into a prompt without this wrapper.
    """
    if isinstance(content, (dict, list)):
        raw_str = json.dumps(content, indent=2, default=str)
    else:
        raw_str = str(content) if content is not None else ""

    escaped = escape_untrusted_delimiters(raw_str)

    header = f"[{label}]\n" if label else ""
    return f"{UNTRUSTED_OPEN}\n{header}{escaped}\n{UNTRUSTED_CLOSE}"


def detect_direct_destructive_intent(user_input: str) -> Tuple[bool, Optional[str]]:
    """
    Deterministic pre-check detecting explicit destructive, modifying, or internal schema requests.
    Handles SQL comment tricks, stacked statements, and direct natural language commands.
    Returns (is_destructive, reason).
    """
    cleaned = user_input.strip()

    # Normalize comments to detect hidden SQL tricks (e.g. DROP/**/TABLE or --\nDELETE)
    normalized = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)
    normalized = re.sub(r"--[^\r\n]*", " ", normalized)

    # Check for direct SQL patterns in both raw and comment-stripped text
    for text_to_check in (cleaned, normalized):
        for pat in DESTRUCTIVE_PATTERNS:
            match = re.search(pat, text_to_check, re.IGNORECASE)
            if match:
                matched_kw = match.group(0).strip()
                return True, f"Prohibited operation '{matched_kw}' detected. QueryPilot permits only read-only analytical queries."

    # Check for stacked statements with semicolons (e.g., "SELECT 1; DROP TABLE...")
    if ";" in normalized:
        parts = [p.strip() for p in normalized.split(";") if p.strip()]
        if len(parts) > 1:
            for part in parts:
                for pat in DESTRUCTIVE_PATTERNS:
                    if re.search(pat, part, re.IGNORECASE):
                        return True, "Stacked statements containing prohibited operations are rejected."

    # Check for plain English destructive commands
    for pat in PLAIN_ENGLISH_DESTRUCTIVE:
        if re.search(pat, normalized, re.IGNORECASE):
            return True, "Destructive operations are prohibited. QueryPilot permits only read-only analytical queries."

    return False, None
