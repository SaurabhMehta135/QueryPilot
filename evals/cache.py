"""
evals/cache.py - Prompt-hash response caching for resumable, quota-efficient evaluations.
Stores LLM completions on disk keyed by SHA-256(provider + model + system_instruction + prompt).
Guarantees evaluation runs can be stopped and resumed without re-calling the API or losing progress.
"""

import os
import json
import hashlib
from typing import Optional, Dict, Any

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def compute_cache_key(provider: str, model: str, prompt: str, system_instruction: Optional[str] = None) -> str:
    payload = f"{provider}:{model}:{system_instruction or ''}:{prompt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached_response(key: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def set_cached_response(key: str, data: Dict[str, Any]):
    path = os.path.join(CACHE_DIR, f"{key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def clear_cache():
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, f))
