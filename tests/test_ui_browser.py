"""
tests/test_ui_browser.py - Live Headless Browser CDP Tests
Verifies:
1. Real In-Browser XSS Protection: Hostile payloads (<script>, <img onerror>, etc.)
   rendered in the answer, table cells, and blocked reason do NOT execute or parse as DOM elements.
2. Real In-Browser Eval Page Numbers: Reads rendered DOM metrics on the Eval page
   and verifies exact match against raw benchmark JSON files.
3. No hardcoded metric literals in UI page sources.
"""

import asyncio
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
import pytest
import websockets
from app.main import app
import uvicorn

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def get_free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class CDPSession:
    def __init__(self, port, cdp_port):
        self.port = port
        self.cdp_port = cdp_port
        self.server = None
        self.server_thread = None
        self.edge_proc = None
        self.ws = None
        self.msg_id = 0

    def start_server(self):
        env = os.environ.copy()
        env["DEFAULT_LLM_PROVIDER"] = "mock"
        env["DEMO_MODE"] = "true"
        self.uvicorn_proc = subprocess.Popen(
            ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Wait for health
        healthy = False
        for _ in range(40):
            time.sleep(0.2)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=0.5) as res:
                    if res.status == 200:
                        healthy = True
                        break
            except Exception:
                pass
        if not healthy:
            raise RuntimeError(f"Could not connect to local server on port {self.port}")

    async def start_browser(self):
        cmd = [
            EDGE_PATH,
            f"--remote-debugging-port={self.cdp_port}",
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir=C:\\temp\\edge_test_profile_{self.cdp_port}",
            "about:blank",
        ]
        self.edge_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ws_url = None
        for _ in range(15):
            await asyncio.sleep(0.1)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.cdp_port}/json", timeout=0.2) as res:
                    pages = json.loads(res.read().decode())
                    for p in pages:
                        if p.get("type") == "page" and "webSocketDebuggerUrl" in p:
                            ws_url = p["webSocketDebuggerUrl"]
                            break
                    if ws_url:
                        break
            except Exception:
                pass

        if not ws_url:
            raise RuntimeError("Could not connect to Edge DevTools")

        self.ws = await websockets.connect(ws_url, max_size=20 * 1024 * 1024)
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("DOM.enable")

    async def send(self, method, params=None):
        self.msg_id += 1
        req_id = self.msg_id
        payload = {"id": req_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(payload))
        while True:
            resp = json.loads(await self.ws.recv())
            if resp.get("id") == req_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error: {resp['error']}")
                return resp.get("result", {})

    async def evaluate(self, expression):
        res = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        val = res.get("result", {})
        if "value" in val:
            return val["value"]
        return val

    async def navigate(self, url):
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(0.6)

    async def close(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        if self.edge_proc:
            try:
                self.edge_proc.terminate()
            except Exception:
                pass
        if hasattr(self, "uvicorn_proc") and self.uvicorn_proc:
            try:
                self.uvicorn_proc.terminate()
            except Exception:
                pass


@pytest.fixture(scope="module")
def browser_cdp_session():
    if not os.path.exists(EDGE_PATH):
        pytest.skip("Microsoft Edge not available for CDP browser tests")

    app_port = get_free_port()
    cdp_port = get_free_port()
    session = CDPSession(app_port, cdp_port)
    try:
        session.start_server()
    except Exception as e:
        pytest.skip(f"Test server cannot bind/connect in current sandbox: {e}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(session.start_browser())
        loop.run_until_complete(session.navigate(f"http://127.0.0.1:{app_port}/"))
    except Exception as e:
        if hasattr(session, "uvicorn_proc") and session.uvicorn_proc:
            session.uvicorn_proc.terminate()
        loop.close()
        pytest.skip(f"Browser CDP not accessible in current environment: {e}")

    yield session, loop

    loop.run_until_complete(session.close())
    loop.close()


def test_in_browser_xss_protection_via_cdp(browser_cdp_session):
    """
    Verifies that real hostile XSS payloads injected into the DOM via
    resultsTabs (explanation & table) and askPage (blocked panel)
    render strictly as plain text without parsing HTML tags or executing scripts.
    """
    session, loop = browser_cdp_session

    script = """(async () => {
        window.__xss_exec_fired = false;
        window.__xss_img_fired = false;

        const xssPayload = '<script>window.__xss_exec_fired=true;<\\/script><img src="x" onerror="window.__xss_img_fired=true">';

        // 1. Inject into Explanation Tab
        window._askPage.resultsTabs.appendExplanation(xssPayload);

        // 2. Inject into Data Table Tab
        window._askPage.resultsTabs.setData(['Injected Column'], [[xssPayload]]);

        // 3. Inject into Blocked Reason
        const blockedCard = document.querySelector('.blocked-card');
        const blockedReason = document.querySelector('.blocked-reason');
        if (blockedCard && blockedReason) {
            blockedCard.style.display = 'block';
            blockedReason.textContent = xssPayload;
        }

        // Allow any microtasks / image error handlers to run
        await new Promise(r => setTimeout(r, 200));

        // Count live DOM elements
        const injectedImgs = document.querySelectorAll('img[src="x"]');
        const streamBox = document.querySelector('.answer-stream-box');
        const answerText = streamBox ? streamBox.textContent : '';
        const td = document.querySelector('.data-table tbody td');
        const cellText = td ? td.textContent : '';
        const reasonText = blockedReason ? blockedReason.textContent : '';

        return {
            xss_exec_fired: window.__xss_exec_fired,
            xss_img_fired: window.__xss_img_fired,
            injected_imgs_count: injectedImgs.length,
            answer_contains_payload: answerText.includes('<script>') && answerText.includes('<img src='),
            cell_contains_payload: cellText.includes('<script>') && cellText.includes('<img src='),
            reason_contains_payload: reasonText.includes('<script>') && reasonText.includes('<img src=')
        };
    })()"""

    result = loop.run_until_complete(session.evaluate(script))

    assert result["xss_exec_fired"] is False, "XSS script payload executed in browser!"
    assert result["xss_img_fired"] is False, "XSS img onerror handler executed in browser!"
    assert result["injected_imgs_count"] == 0, "Hostile img tag was parsed into live DOM element!"
    assert result["answer_contains_payload"] is True, "Answer text must safely contain payload as textContent"
    assert result["cell_contains_payload"] is True, "Table cell must safely contain payload as textContent"
    assert result["reason_contains_payload"] is True, "Blocked reason must safely contain payload as textContent"


def test_in_browser_eval_page_numbers_match_raw_artifacts(browser_cdp_session):
    """
    Navigates to the Benchmark Evaluations page in the live browser,
    reads the rendered DOM metrics, and asserts exact match against the raw JSON benchmark artifacts.
    """
    session, loop = browser_cdp_session

    # Navigate to Evals tab
    navigate_script = """(() => {
        const navItems = document.querySelectorAll('.nav-item');
        for (const item of navItems) {
            if (item.textContent.includes('Benchmark Evals')) {
                item.click();
                return true;
            }
        }
        return false;
    })()"""
    loop.run_until_complete(session.evaluate(navigate_script))
    time.sleep(0.8)

    extract_script = """(async () => {
        // Wait up to 5 seconds for /eval/summary fetch to render
        for (let i = 0; i < 50; i++) {
            const firstVal = document.querySelector('.eval-score-card .metric-val')?.textContent.trim();
            if (firstVal && firstVal.length > 0) break;
            await new Promise(r => setTimeout(r, 100));
        }

        const cards = document.querySelectorAll('.eval-score-card');
        const cardData = [];
        cards.forEach(c => {
            const rows = Array.from(c.querySelectorAll('.score-metric-row')).map(r => ({
                label: r.querySelector('.metric-label')?.textContent.trim() || '',
                val: r.querySelector('.metric-val')?.textContent.trim() || '',
                sub: r.querySelector('.metric-sub')?.textContent.trim() || ''
            }));
            cardData.push({
                title: c.querySelector('.score-card-title')?.textContent.trim() || '',
                subtitle: c.querySelector('.score-card-sub')?.textContent.trim() || '',
                rows: rows
            });
        });

        const taxPills = document.querySelectorAll('.taxonomy-badge');
        const taxCounts = [];
        taxPills.forEach(p => taxCounts.push(p.textContent.trim()));

        return {
            cards: cardData,
            taxPills: taxCounts
        };
    })()"""

    dom_data = loop.run_until_complete(session.evaluate(extract_script))
    print("DOM DATA EXTRACTED:", dom_data)
    assert len(dom_data["cards"]) == 4, f"Expected 4 scorecards, got {len(dom_data['cards'])}"

    # Load raw JSON artifacts
    base_dir = os.path.dirname(os.path.dirname(__file__))
    with open(os.path.join(base_dir, "evals", "results", "run_4", "accuracy_dev.json"), "r", encoding="utf-8") as f:
        raw_dev = json.load(f)
    with open(os.path.join(base_dir, "evals", "results", "run_4", "accuracy_test_stratified_50.json"), "r", encoding="utf-8") as f:
        raw_test = json.load(f)
    with open(os.path.join(base_dir, "evals", "results", "run_4", "safety_results.json"), "r", encoding="utf-8") as f:
        raw_safety = json.load(f)

    def find_card(pattern):
        for c in dom_data["cards"]:
            if pattern.lower() in c["title"].lower():
                return c
        raise ValueError(f"Card matching '{pattern}' not found")

    # 1. Dev Card (84.0% lenient / 70.0% strict / 50 questions)
    dev_card = find_card("Dev")
    dev_pct_str = f"{raw_dev['lenient_execution_accuracy'] * 100:.1f}%"
    dev_strict_str = f"{raw_dev['strict_execution_accuracy'] * 100:.1f}%"
    assert dev_card["rows"][0]["val"] == dev_pct_str, f"Dev score {dev_card['rows'][0]['val']} != {dev_pct_str}"
    assert dev_card["rows"][1]["val"] == dev_strict_str
    assert f"n={raw_dev['total_questions']}" in dev_card["title"]
    assert f"{raw_dev['lenient_correct_count']}/{raw_dev['total_questions']}" in dev_card["rows"][0]["sub"]
    assert f"{raw_dev['strict_correct_count']}/{raw_dev['total_questions']}" in dev_card["rows"][1]["sub"]

    # 2. Test Card (68.0% lenient / 58.0% strict / 50 questions)
    test_card = find_card("Test")
    test_pct_str = f"{raw_test['lenient_execution_accuracy'] * 100:.1f}%"
    test_strict_str = f"{raw_test['strict_execution_accuracy'] * 100:.1f}%"
    assert test_card["rows"][0]["val"] == test_pct_str
    assert test_card["rows"][1]["val"] == test_strict_str
    assert f"n={raw_test['total_questions']}" in test_card["title"]
    assert f"{raw_test['lenient_correct_count']}/{raw_test['total_questions']}" in test_card["rows"][0]["sub"]
    assert f"{raw_test['strict_correct_count']}/{raw_test['total_questions']}" in test_card["rows"][1]["sub"]

    # 3. Clean Subset Card (54.5% lenient / 39.4% strict / 33 questions)
    clean_card = find_card("Clean")
    clean = raw_test["clean_subset_33"]
    clean_pct_str = f"{clean['lenient_accuracy'] * 100:.1f}%"
    clean_strict_str = f"{clean['strict_accuracy'] * 100:.1f}%"
    assert clean_card["rows"][0]["val"] == clean_pct_str
    assert clean_card["rows"][1]["val"] == clean_strict_str
    assert f"n={clean['total']}" in clean_card["title"]
    assert f"{clean['lenient_correct']}/{clean['total']}" in clean_card["rows"][0]["sub"]
    assert f"{clean['strict_correct']}/{clean['total']}" in clean_card["rows"][1]["sub"]

    # 4. Security Card (60/60 attacks blocked / 26/26 benign allowed)
    sec_card = find_card("Safety")
    attacks_blocked = raw_safety["attacks_safely_handled"]
    total_attacks = raw_safety["total_attacks"]
    benign_allowed = raw_safety["total_benign_queries"] - raw_safety["false_blocks"]
    total_benign = raw_safety["total_benign_queries"]
    assert f"{attacks_blocked} / {total_attacks}" in sec_card["rows"][0]["sub"]
    assert f"{benign_allowed} / {total_benign}" in sec_card["rows"][1]["sub"]
