"""
tests/conftest.py - Pytest fixtures and live API guard.
Ensures that no test in the test suite makes live external API calls unless explicitly
requested via pytest --run-live.
"""

import pytest
from app.config import settings


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live tests that make real external network LLM calls",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "live: mark test as requiring external network access to LLM APIs")


@pytest.fixture(autouse=True)
def isolate_from_live_api_keys(monkeypatch, request):
    """
    Auto-used across all tests:
    Unless --run-live is explicitly passed, neutralizes environment API keys
    and enforces provider='mock'.
    """
    if not request.config.getoption("--run-live", default=False):
        monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "mock")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
        monkeypatch.setattr(settings, "GROQ_API_KEY", None)
        monkeypatch.setattr(settings, "OPENAI_API_KEY", None)


@pytest.fixture(scope="session")
def session_mcp_client():
    """
    Session-scoped MCP client fixture.
    Provides persistent, high-performance database tool execution across the entire test session.
    """
    from app.mcp_client.client import DirectMCPClient
    return DirectMCPClient()
