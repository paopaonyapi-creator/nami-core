#!/usr/bin/env python3
"""Test webhook + metrics endpoints."""
import json, urllib.request

API = "http://127.0.0.1:8092"

# Test webhook
data = json.dumps({"source": "test", "event": "ping", "data": {"msg": "hello"}}).encode("utf-8")
req = urllib.request.Request(f"{API}/webhook", data=data, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        print("Webhook:", json.loads(resp.read().decode("utf-8")))
except urllib.error.HTTPError as e:
    print(f"Webhook error {e.code}:", json.loads(e.read().decode("utf-8")))

# Test metrics
req = urllib.request.Request(f"{API}/metrics")
with urllib.request.urlopen(req, timeout=5) as resp:
    print("Metrics:", json.loads(resp.read().decode("utf-8")))
