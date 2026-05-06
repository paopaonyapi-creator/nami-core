#!/usr/bin/env python3
"""Test nami-core API key auth."""
import json, urllib.request

API = "http://127.0.0.1:8092"
PAYLOAD = json.dumps({"worker": "lottery", "action": "vip", "payload": {"region": "lao"}}).encode("utf-8")

# Read API key
try:
    with open("/etc/nami-harness/nami_api_key") as f:
        api_key = f.read().strip()
    print(f"API Key: {api_key[:8]}...")
except:
    api_key = ""
    print("No API key file found, testing without auth")

# Test without auth (should 401 if key is set)
print("\n=== No auth ===")
try:
    req = urllib.request.Request(f"{API}/dispatch", data=PAYLOAD, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"Status: {resp.status}")
        print(json.loads(resp.read().decode("utf-8")))
except urllib.error.HTTPError as e:
    print(f"Status: {e.code} (expected 401 if auth enabled)")
    print(json.loads(e.read().decode("utf-8")))

# Test with auth (should 200)
if api_key:
    print("\n=== With auth ===")
    try:
        req = urllib.request.Request(f"{API}/dispatch", data=PAYLOAD,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Status: {resp.status}")
            data = json.loads(resp.read().decode("utf-8"))
            print(f"OK: {data.get('ok')}")
            if data.get("output"):
                picks = data["output"].get("db_picks", data["output"])
                print(f"1D: {picks.get('1d', [])}")
                print(f"2D: {picks.get('2d_main', [])}")
    except urllib.error.HTTPError as e:
        print(f"Status: {e.code}")
        print(json.loads(e.read().decode("utf-8")))

# Test GET /health (should work without auth)
print("\n=== GET /health (no auth needed) ===")
try:
    req = urllib.request.Request(f"{API}/health")
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(f"Status: {resp.status} OK")
except Exception as e:
    print(f"Error: {e}")
