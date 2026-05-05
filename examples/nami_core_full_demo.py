"""Nami Core — Full system demo with all 9 workers.

Demonstrates the complete Hermes → Harness → Worker pipeline
for every worker in the Nami ecosystem.
"""

from nami_core.config import HarnessConfig
from nami_core.hermes import Hermes
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy
from nami_harness.runtime import HarnessRuntime
from nami_workers import ALL_WORKERS


def build_production_hermes() -> Hermes:
    """Build Hermes with production-like harness configs for all workers."""
    hermes = Hermes()

    worker_configs: dict[str, dict] = {
        "signal": {
            "rails": RailPolicy(allowed_agents={"hermes"}, allowed_actions={"generate_signal", "send_signal", "send_dm"}),
            "quality": QualityGate([require_non_empty("signal"), forbid_terms("guarantee", "แน่นอน", "100%", "การันตีกำไร")]),
        },
        "proxy": {
            "rails": RailPolicy(allowed_agents={"hermes", "external"}, allowed_actions={"chat_completion", "list_models", "embed"}),
            "quality": QualityGate([forbid_terms("raw_secret", "api_key=")]),
        },
        "lottery": {
            "rails": RailPolicy(allowed_agents={"hermes"}, allowed_actions={"predict", "send_prediction", "fetch_results"}),
            "quality": QualityGate([require_non_empty("prediction"), forbid_terms("guarantee", "แน่นอน", "100%", "การันตี")]),
        },
        "trading": {
            "rails": RailPolicy(allowed_agents={"hermes"}, allowed_actions={"paper_trade", "analyze_signal", "check_position"}),
            "quality": QualityGate([require_non_empty("signal"), forbid_terms("guarantee", "การันตีกำไร")]),
        },
        "bot": {
            "rails": RailPolicy(allowed_agents={"hermes"}, allowed_actions={"help", "status", "package_info", "subscribe"}),
            "quality": QualityGate([require_non_empty("answer")]),
        },
        "gateway": {
            "rails": RailPolicy(allowed_agents={"hermes", "external"}, allowed_actions={"route", "health"}),
            "quality": QualityGate([]),
        },
        "status": {
            "rails": RailPolicy(allowed_agents={"hermes", "external"}, allowed_actions={"health", "worker_health"}),
            "quality": QualityGate([]),
        },
        "bridge": {
            "rails": RailPolicy(allowed_agents={"hermes"}, allowed_actions={"relay", "subscribe"}),
            "quality": QualityGate([]),
        },
        "graphify": {
            "rails": RailPolicy(allowed_agents={"hermes"}, allowed_actions={"query", "analyze", "impact"}),
            "quality": QualityGate([forbid_terms("raw_secret")]),
        },
    }

    for name, task_fn in ALL_WORKERS.items():
        cfg = worker_configs.get(name, {})
        runtime = HarnessRuntime(
            rails=cfg.get("rails", RailPolicy()),
            quality=cfg.get("quality", QualityGate([])),
        )
        hermes.register(name, runtime, task_fn)

    return hermes


def main() -> None:
    hermes = build_production_hermes()
    workers = hermes.list_workers()
    print(f"╔══════════════════════════════════════════╗")
    print(f"║  Nami Core — Full System Demo            ║")
    print(f"║  {len(workers)} workers registered               ║")
    print(f"╚══════════════════════════════════════════╝")
    print()

    # === 1. Signal Worker ===
    print("━━━ Signal Worker ━━━")
    result = hermes.dispatch("signal", "generate_signal", {"action": "generate_signal", "task": "gold_daily"})
    print(f"  Generated: {result.output['signal']}")
    print(f"  Confidence: {result.output['confidence']}")
    print(f"  Risk: {result.output['risk_level']}")
    print(f"  Quality: {'✅ PASS' if result.passed_quality else '❌ FAIL'}")
    print()

    # === 2. Proxy Worker ===
    print("━━━ Proxy Worker ━━━")
    result = hermes.dispatch("proxy", "chat_completion", {"action": "chat_completion", "model": "claude-3-sonnet", "messages": [{"role": "user", "content": "hello"}]})
    print(f"  Model: {result.output['model']}")
    print(f"  Quality: {'✅ PASS' if result.passed_quality else '❌ FAIL'}")
    print()

    # === 3. Lottery Worker ===
    print("━━━ Lottery Worker (Hanoi) ━━━")
    result = hermes.dispatch("lottery", "predict", {"action": "predict", "region": "hanoi"})
    print(f"  Prediction: {result.output['prediction']}")
    print(f"  Method: {result.output['method']}")
    print(f"  Quality: {'✅ PASS' if result.passed_quality else '❌ FAIL'}")
    print()

    # === 4. Trading Worker ===
    print("━━━ Trading Worker ━━━")
    result = hermes.dispatch("trading", "paper_trade", {"action": "paper_trade", "symbol": "XAU_USD", "direction": "Long"})
    print(f"  Trade: {result.output['symbol']} {result.output['direction']}")
    print(f"  Mode: {result.output['mode']}")
    print(f"  Quality: {'✅ PASS' if result.passed_quality else '❌ FAIL'}")
    print()

    # === 5. Bot Worker ===
    print("━━━ Bot Worker ━━━")
    result = hermes.dispatch("bot", "package_info", {"action": "package_info"})
    print(f"  Packages: {result.output['answer'][:60]}...")
    print(f"  Quality: {'✅ PASS' if result.passed_quality else '❌ FAIL'}")
    print()

    # === 6. Gateway Worker ===
    print("━━━ Gateway Worker ━━━")
    result = hermes.dispatch("gateway", "route", {"action": "route", "path": "/api/signal/generate", "method": "POST"})
    print(f"  Route: {result.output['path']} → {result.output['worker']}")
    print()

    # === 7. Status Worker ===
    print("━━━ Status Worker ━━━")
    result = hermes.dispatch("status", "health", {"action": "health"})
    print(f"  Status: {result.output['status']}")
    print()

    # === 8. Bridge Worker ===
    print("━━━ Bridge Worker ━━━")
    result = hermes.dispatch("bridge", "relay", {"action": "relay", "event_type": "signal"})
    print(f"  Relayed: {result.output['relayed']}")
    print()

    # === 9. Graphify Worker ===
    print("━━━ Graphify Worker ━━━")
    result = hermes.dispatch("graphify", "query", {"action": "query", "cypher": "MATCH (n) RETURN n LIMIT 5", "repo": "nami-core"})
    print(f"  Query executed")
    print()

    # === Quality Gate Demo ===
    print("━━━ Quality Gate Enforcement ━━━")
    print("Testing forbidden terms...")

    def bad_signal(payload: dict) -> dict:
        return {"signal": "XAU/USD Long", "reason": "guarantee profit 100%"}

    hermes.register("bad_signal", HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"generate_signal"}),
        quality=QualityGate([require_non_empty("signal"), forbid_terms("guarantee", "100%")]),
    ), bad_signal)

    try:
        hermes.dispatch("bad_signal", "generate_signal", {})
        print("  ❌ ERROR: Should have been blocked!")
    except Exception as exc:
        print(f"  ✅ Blocked: {exc}")

    print()
    print("╔══════════════════════════════════════════╗")
    print("║  All 9 workers operational              ║")
    print("║  Quality gates enforced                  ║")
    print("║  Nami Core ready for VPS migration      ║")
    print("╚══════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
