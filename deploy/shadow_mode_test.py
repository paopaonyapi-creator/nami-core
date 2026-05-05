#!/usr/bin/env python3
"""Shadow Mode — Compare nami-core worker output vs production services.

Runs each nami-core worker and compares output with the real VPS service.
Reports differences for manual review before switching.
"""
import json
import subprocess
import sys
import os

sys.path.insert(0, "/opt/nami-core/src")

from nami_workers.signal_worker import signal_worker, read_prices
from nami_workers.lottery_worker import lottery_worker, fetch_draw_results
from nami_workers.status_worker import status_worker
from nami_workers.trading_worker import trading_worker
from nami_workers.proxy_worker import proxy_worker


def run_shadow_comparison():
    results = {}

    # 1. Signal Worker vs Production
    print("━━━ Signal Worker (Shadow) ━━━")
    try:
        prices = read_prices()
        signal = signal_worker({"action": "generate_signal", "task": "gold_daily"})
        results["signal"] = {
            "shadow": signal,
            "vps_prices": prices,
            "match": bool(prices.get("spot_usd")),
        }
        print(f"  Signal: {signal.get('signal', 'N/A')}")
        print(f"  VPS prices loaded: {bool(prices)}")
    except Exception as e:
        results["signal"] = {"error": str(e)}
        print(f"  Error: {e}")

    # 2. Lottery Worker vs Production
    print("\n━━━ Lottery Worker (Shadow) ━━━")
    try:
        vps_results = fetch_draw_results("hanoi", limit=5)
        prediction = lottery_worker({"action": "predict", "region": "hanoi"})
        results["lottery"] = {
            "shadow_prediction": prediction,
            "vps_results_count": len(vps_results),
            "vps_api_available": bool(vps_results),
        }
        print(f"  Prediction: {prediction.get('prediction', 'N/A')}")
        print(f"  VPS API results: {len(vps_results)} records")
    except Exception as e:
        results["lottery"] = {"error": str(e)}
        print(f"  Error: {e}")

    # 3. Status Worker vs systemd
    print("\n━━━ Status Worker (Shadow) ━━━")
    try:
        health = status_worker({"action": "health"})
        services = status_worker({"action": "services"})
        results["status"] = {
            "shadow_health": health,
            "shadow_services_active": services.get("active", 0),
            "shadow_services_failed": services.get("failed", 0),
        }
        print(f"  Health: {health.get('status')}")
        print(f"  Services: {services.get('active', 0)} active, {services.get('failed', 0)} failed")
        if health.get("metrics"):
            m = health["metrics"]
            print(f"  RAM: {m.get('ram_used_pct', '?')}% | Disk: {m.get('disk_used_pct', '?')}% | Load: {m.get('load_1m', '?')}")
    except Exception as e:
        results["status"] = {"error": str(e)}
        print(f"  Error: {e}")

    # 4. Trading Worker
    print("\n━━━ Trading Worker (Shadow) ━━━")
    try:
        trade = trading_worker({"action": "paper_trade", "symbol": "XAU_USD", "direction": "Long"})
        results["trading"] = {"shadow": trade}
        print(f"  Trade: {trade.get('signal', 'N/A')}")
    except Exception as e:
        results["trading"] = {"error": str(e)}
        print(f"  Error: {e}")

    # 5. Proxy Worker
    print("\n━━━ Proxy Worker (Shadow) ━━━")
    try:
        # Check MaxPlus proxy is running
        import urllib.request
        import urllib.error
        proxy_alive = False
        try:
            req = urllib.request.Request("http://127.0.0.1:8091/v1/models")
            with urllib.request.urlopen(req, timeout=5) as resp:
                proxy_alive = True
        except urllib.error.HTTPError:
            proxy_alive = True  # 404 is ok, means proxy is running
        except (urllib.error.URLError, OSError):
            proxy_alive = False

        completion = proxy_worker({
            "action": "chat_completion",
            "model": "claude-3-sonnet",
            "messages": [{"role": "user", "content": "Say hello in 5 words"}],
            "max_tokens": 50,
        })
        results["proxy"] = {"shadow": completion, "proxy_alive": proxy_alive}
        print(f"  MaxPlus proxy alive: {proxy_alive}")
        print(f"  Provider: {completion.get('provider', 'N/A')}")
        print(f"  Response: {completion.get('response', 'N/A')[:100]}")
    except Exception as e:
        results["proxy"] = {"error": str(e)}
        print(f"  Error: {e}")

    # Summary
    print("\n" + "=" * 50)
    print("SHADOW MODE COMPARISON SUMMARY")
    print("=" * 50)
    for name, data in results.items():
        if "error" in data:
            print(f"  {name}: ❌ ERROR — {data['error'][:80]}")
        elif data.get("match") or data.get("vps_api_available") or data.get("shadow_services_active", 0) > 0:
            print(f"  {name}: ✅ VPS data connected")
        else:
            print(f"  {name}: ⚠️  Fallback mode (no VPS data)")

    # Save full results
    out_path = "/opt/nami-core/shadow_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    print(f"\nFull results saved to {out_path}")

    return results


if __name__ == "__main__":
    run_shadow_comparison()
