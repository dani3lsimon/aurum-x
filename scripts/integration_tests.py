"""
scripts/integration_tests.py
Integration tests for AURUM-X — runs against production Railway backend.
Usage: python scripts/integration_tests.py [--local]
"""
import sys
import json
import time
import httpx
import asyncio
import argparse
import websockets

BASE_LOCAL = "http://127.0.0.1:8000"
BASE_PROD  = "https://aurum-x-backend-production.up.railway.app"

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
SKIP = "\033[93m[SKIP]\033[0m"

results = {"passed": 0, "failed": 0, "skipped": 0}


def ok(name: str, detail: str = ""):
    results["passed"] += 1
    print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    results["failed"] += 1
    print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))


def skip(name: str, reason: str = ""):
    results["skipped"] += 1
    print(f"  {SKIP} {name}" + (f" — {reason}" if reason else ""))


def test_http(client: httpx.Client, base: str):
    print("\n--- HTTP Endpoints ---")

    # Health
    try:
        r = client.get(f"{base}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "operational"
        ok("GET /health", f"v{data.get('version','?')}")
    except Exception as e:
        fail("GET /health", str(e))

    # Forecast latest
    try:
        r = client.get(f"{base}/forecast/latest")
        assert r.status_code == 200
        ok("GET /forecast/latest", f"keys={list(r.json().keys())[:4]}")
    except Exception as e:
        fail("GET /forecast/latest", str(e))

    # Forecast history
    try:
        r = client.get(f"{base}/forecast/history?hours=48")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ok("GET /forecast/history", f"{len(data)} records")
    except Exception as e:
        fail("GET /forecast/history", str(e))

    # Agent scores
    try:
        r = client.get(f"{base}/agents/scores")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ok("GET /agents/scores", f"{len(data)} agents")
    except Exception as e:
        fail("GET /agents/scores", str(e))

    # Agent history
    try:
        r = client.get(f"{base}/agents/history/macro_agent?limit=5")
        assert r.status_code == 200
        ok("GET /agents/history/macro_agent", f"{len(r.json())} entries")
    except Exception as e:
        fail("GET /agents/history/macro_agent", str(e))

    # Scenarios
    try:
        r = client.get(f"{base}/scenarios/latest")
        assert r.status_code == 200
        ok("GET /scenarios/latest", f"{len(r.json())} scenarios")
    except Exception as e:
        fail("GET /scenarios/latest", str(e))

    # Alerts
    try:
        r = client.get(f"{base}/alerts/recent")
        assert r.status_code == 200
        ok("GET /alerts/recent", f"{len(r.json())} alerts")
    except Exception as e:
        fail("GET /alerts/recent", str(e))

    # Calendar
    try:
        r = client.get(f"{base}/calendar/upcoming")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ok("GET /calendar/upcoming", f"{len(data)} releases")
    except Exception as e:
        fail("GET /calendar/upcoming", str(e))

    # Manual trigger
    try:
        r = client.post(f"{base}/forecast/trigger", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "triggered"
        ok("POST /forecast/trigger", data["message"])
    except Exception as e:
        fail("POST /forecast/trigger", str(e))


async def test_websocket(base: str):
    print("\n--- WebSocket ---")
    ws_url = base.replace("https://", "wss://").replace("http://", "ws://") + "/forecast/ws"
    try:
        async with websockets.connect(ws_url, open_timeout=10, close_timeout=5) as ws:
            msg_raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(msg_raw)
            assert "type" in msg or "data" in msg or isinstance(msg, dict)
            ok("WebSocket /forecast/ws", f"type={msg.get('type','?')}")
    except Exception as e:
        fail("WebSocket /forecast/ws", str(e))


def test_cors(client: httpx.Client, base: str):
    print("\n--- CORS ---")
    origins = [
        "https://aurum-x-one.vercel.app",
        "http://localhost:3000",
    ]
    for origin in origins:
        try:
            r = client.options(f"{base}/health", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            })
            acao = r.headers.get("access-control-allow-origin", "")
            if acao in (origin, "*"):
                ok(f"CORS from {origin}")
            else:
                fail(f"CORS from {origin}", f"got: '{acao}'")
        except Exception as e:
            fail(f"CORS from {origin}", str(e))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Run against localhost:8000")
    args = parser.parse_args()

    base = BASE_LOCAL if args.local else BASE_PROD
    print("\nAURUM-X Integration Tests")
    print(f"Target: {base}\n")

    with httpx.Client(timeout=30) as client:
        test_http(client, base)
        test_cors(client, base)

    asyncio.run(test_websocket(base))

    total = results["passed"] + results["failed"] + results["skipped"]
    print(f"\nResults: {results['passed']}/{total} passed  |  {results['failed']} failed  |  {results['skipped']} skipped\n")

    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
