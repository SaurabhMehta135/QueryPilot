"""
app/agents/prompt_loader.py - Loads system prompts from the prompts/ directory at runtime.
"""

import os
from functools import lru_cache

PROMPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")
)


@lru_cache(maxsize=16)
def load_prompt(filename: str) -> str:
    """Loads and returns the text content of a markdown prompt file from prompts/."""
    file_path = os.path.join(PROMPTS_DIR, filename)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()
