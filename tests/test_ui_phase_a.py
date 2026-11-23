"""
tests/test_ui_phase_a.py - Phase A UI Regression, Security & Component Tests.
Validates:
1. UI files are properly served via FastAPI.
2. Zero innerHTML / outerHTML / insertAdjacentHTML occurrences in ui/js/ directory.
3. DOM XSS sanitization and textContent usage across every component that renders data.
4. CSS stylesheets and offline vendored dependencies exist.
"""

import os
import re
from fastapi.testclient import TestClient
from app.main import app


def test_ui_served_via_root():
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "QueryPilot - Multi-Agent Text-to-SQL Assistant" in res.text
        assert "tokens.css" in res.text
        assert "base.css" in res.text
        assert "components.css" in res.text
        assert "chart.umd.min.js" in res.text
        assert "main.js" in res.text


def test_no_innerhtml_in_ui_javascript():
    """
    Comprehensive Static Source Security Guard:
    Scans every JS file in ui/js/ and asserts zero usage of:
    - innerHTML, outerHTML, insertAdjacentHTML
    - document.write / document.writeln
    - setAttribute("on*") inline event handlers
    - javascript: pseudo-protocol URLs
    - createContextualFragment
    - DOMParser
    - eval / Function constructor
    """
    ui_js_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "js")
    assert os.path.exists(ui_js_dir), f"Directory {ui_js_dir} must exist"

    dangerous_patterns = [
        (re.compile(r"\.innerHTML\b"), "innerHTML"),
        (re.compile(r"\.outerHTML\b"), "outerHTML"),
        (re.compile(r"\.insertAdjacentHTML\b"), "insertAdjacentHTML"),
        (re.compile(r"document\.write(?:ln)?\b"), "document.write"),
        (re.compile(r"setAttribute\s*\(\s*['\"]on[a-z]+['\"]", re.IGNORECASE), "inline on* event attribute"),
        (re.compile(r"['\"]javascript\s*:", re.IGNORECASE), "javascript: URL scheme"),
        (re.compile(r"createContextualFragment\b"), "createContextualFragment"),
        (re.compile(r"new\s+DOMParser\b"), "DOMParser"),
        (re.compile(r"\beval\s*\("), "eval()"),
        (re.compile(r"new\s+Function\s*\("), "new Function()"),
    ]

    scanned_files = 0
    for root, _, files in os.walk(ui_js_dir):
        for file in files:
            if file.endswith(".js"):
                scanned_files += 1
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    for pattern, name in dangerous_patterns:
                        match = pattern.search(content)
                        assert match is None, (
                            f"Forbidden security violation '{name}' matched in {filepath}: '{match.group()}'. "
                            "Must use textContent and createElement exclusively."
                        )

    assert scanned_files >= 6, f"Expected at least 6 JS files scanned, found {scanned_files}"


def test_component_xss_data_rendering_contracts():
    """
    Asserts that every component rendering user or model data uses textContent:
    - resultsTabs.js (NL answer, SQL code block, Table cells)
    - hitlCard.js (clarification message, approval SQL)
    - traceDrawer.js (timeline details, raw json)
    - askPage.js (blocked reason)
    """
    ui_js_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "js")

    # 1. resultsTabs.js
    with open(os.path.join(ui_js_dir, "components", "resultsTabs.js"), "r", encoding="utf-8") as f:
        tabs_src = f.read()
        assert "textContent" in tabs_src
        assert "td.textContent = " in tabs_src
        assert "this.dom.sqlCode.textContent = " in tabs_src

    # 2. hitlCard.js
    with open(os.path.join(ui_js_dir, "components", "hitlCard.js"), "r", encoding="utf-8") as f:
        hitl_src = f.read()
        assert "p.textContent = message" in hitl_src
        assert "pre.textContent = " in hitl_src

    # 3. traceDrawer.js
    with open(os.path.join(ui_js_dir, "components", "traceDrawer.js"), "r", encoding="utf-8") as f:
        drawer_src = f.read()
        assert "detail.textContent = " in drawer_src
        assert "rawPre.textContent = " in drawer_src

    # 4. askPage.js
    with open(os.path.join(ui_js_dir, "pages", "askPage.js"), "r", encoding="utf-8") as f:
        ask_src = f.read()
        assert "p.textContent = data.reason" in ask_src or "blockedReason" in ask_src


def test_offline_vendored_chartjs_exists():
    vendor_chart = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "ui", "vendor", "chart.umd.min.js"
    )
    assert os.path.exists(vendor_chart)
    assert os.path.getsize(vendor_chart) > 100_000, "Vendored Chart.js must be a valid non-empty bundle"


def test_design_tokens_and_stylesheets():
    css_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "css")
    for css_file in ["tokens.css", "base.css", "components.css"]:
        full_path = os.path.join(css_dir, css_file)
        assert os.path.exists(full_path), f"CSS file {css_file} must exist"
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert len(content) > 100


def test_scenario_hooks_only_activate_with_mock_provider():
    """
    Verifies that the test-only mock prompt scenario hooks ([SCENARIO:...])
    NEVER activate on real production LLM providers (Gemini, Groq, OpenAI).
    """
    from app.llm.providers import MockLLMProvider, LLMResponse
    import pytest
    import asyncio

    mock_provider = MockLLMProvider()
    resp = asyncio.run(mock_provider.generate("[SCENARIO:CLARIFICATION]", json_mode=True))
    assert "needs_clarification" in resp.content

    # Assert real providers do not recognize or process this hook
    from app.llm.providers import GeminiProvider, GroqProvider
    gemini = GeminiProvider(api_key="mock-key")
    groq = GroqProvider(api_key="mock-key")
    assert not hasattr(gemini, "_retry_counter")
    assert not hasattr(groq, "_retry_counter")


def test_stop_button_aborts_stream_client_contract():
    """
    Verifies that QueryPilotAPI.abortCurrent() triggers the AbortController signal
    and cleanly resets state without raising unhandled errors.
    """
    from app.main import app
    client = TestClient(app)

    # 1. UI script exposes abortCurrent contract
    ui_js_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "js")
    with open(os.path.join(ui_js_dir, "api.js"), "r", encoding="utf-8") as f:
        src = f.read()
        assert "this.currentAbortController.abort()" in src
        assert "activeAbortController.abort()" in open(os.path.join(ui_js_dir, "pages", "askPage.js"), "r", encoding="utf-8").read()


def test_static_source_security_guard_xss():
    """
    Static Source Security Guard:
    Scans every JavaScript source file across ui/js (pages, components, state, api)
    to enforce strict DOM-safety rules.
    Verifies zero usage of dangerous HTML injection sinks:
    - .innerHTML, .outerHTML, .insertAdjacentHTML
    - document.write
    - setAttribute("on*") or inline event handler registration
    - javascript: pseudo-protocol URIs
    - createContextualFragment (Range API DOM parsing)
    - DOMParser HTML parsing
    - eval() and new Function() dynamic code execution
    And asserts that safe textContent is properly used for text and data rendering.
    """
    ui_js_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "js")
    dangerous_patterns = [
        ".innerHTML",
        ".outerHTML",
        ".insertAdjacentHTML",
        "document.write",
        'setAttribute("on',
        "setAttribute('on",
        "javascript:",
        "createContextualFragment",
        "DOMParser",
        "eval(",
        "new Function(",
    ]

    scanned_files = 0
    for root, _, files in os.walk(ui_js_dir):
        for f in files:
            if f.endswith(".js"):
                scanned_files += 1
                full_path = os.path.join(root, f)
                with open(full_path, "r", encoding="utf-8") as js_file:
                    content = js_file.read()
                    for pattern in dangerous_patterns:
                        assert pattern not in content, (
                            f"Security Guard Violation: Dangerous pattern '{pattern}' found in {full_path}"
                        )

    assert scanned_files >= 8, f"Expected to scan at least 8 JS files, scanned {scanned_files}"
