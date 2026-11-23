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
    config.addinivalue_line("markers", "real_stdio: mark test as executing against real stdio MCP server subprocess")


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


@pytest.fixture(autouse=True)
def inject_test_mcp_client(monkeypatch, request):
    """
    Session-wide test fixture:
    Injects high-performance DirectMCPClient into app.main and app.agents.executor
    for test execution, while keeping production default to real MCP stdio server.
    Tests specifically marked with @pytest.mark.real_stdio (test_end_to_end_graph_with_real_stdio_mcp_server,
    test_real_stdio_mcp_server_integration) explicitly instantiate and test MCPDatabaseClient.
    """
    if request.node.get_closest_marker("real_stdio") is None:
        from app.mcp_client.client import DirectMCPClient
        from app import main
        from app.agents import executor
        test_client = DirectMCPClient()
        monkeypatch.setattr(main, "mcp_client", test_client)


@pytest.fixture(scope="session")
def session_mcp_client():
    """
    Session-scoped MCP client fixture.
    Provides persistent, high-performance database tool execution across the entire test session.
    """
    from app.mcp_client.client import DirectMCPClient
    return DirectMCPClient()
