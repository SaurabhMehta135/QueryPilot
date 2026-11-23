import asyncio
import json
import urllib.request
import websockets

async def test():
    with urllib.request.urlopen("http://127.0.0.1:9222/json") as res:
        pages = json.loads(res.read().decode())
        ws_url = [p["webSocketDebuggerUrl"] for p in pages if "http://127.0.0.1:8000" in p.get("url", "")][0]
    async with websockets.connect(ws_url) as ws:
        async def call(method, params=None):
            msg = {"id": 1, "method": method, "params": params or {}}
            await ws.send(json.dumps(msg))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == 1: return r.get("result", {})

        await call("Network.enable")
        await call("Network.setCacheDisabled", {"cacheDisabled": True})
        await call("Page.reload", {"ignoreCache": True})
        await asyncio.sleep(2.0)
        res = await call("Runtime.evaluate", {
            "expression": "import('/static/js/main.js?t=' + Date.now()).then(m => 'Import SUCCESS').catch(e => 'Import ERROR: ' + e.message)",
            "awaitPromise": True
        })
        print("Import with cache bypass:", res.get("result", {}).get("value"))
        res_dom = await call("Runtime.evaluate", {"expression": "document.getElementById('app-root').children.length"})
        print("DOM children:", res_dom.get("result", {}).get("value"))

if __name__ == "__main__":
    asyncio.run(test())
