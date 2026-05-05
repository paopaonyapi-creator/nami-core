"""Nami Core — Full pipeline demo.

Shows how Hermes, Harness, and Workers integrate:
1. Load harness configs from YAML
2. Register workers with their harness runtimes
3. Dispatch tasks through Hermes → Harness → Worker
"""

from nami_core.config import load_harness_config
from nami_core.hermes import Hermes
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy
from nami_harness.runtime import HarnessRuntime
from nami_workers.registry import WorkerRegistry


def signal_worker(payload: dict) -> dict:
    return {
        "signal": "XAU/USD Long @ 2340",
        "reason": "Breakout above resistance with volume confirmation",
        "confidence": "Medium",
    }


def proxy_worker(payload: dict) -> dict:
    return {
        "response": f"LLM response for: {payload.get('prompt', 'unknown')}",
        "model": "claude-3-sonnet",
        "tokens": 150,
    }


def lottery_worker(payload: dict) -> dict:
    return {
        "prediction": "42, 17, 88, 3, 55, 29",
        "confidence": "Low",
        "method": "AI statistical analysis",
    }


def main() -> None:
    # Build Hermes
    hermes = Hermes()

    # Register signal worker with inline harness config
    from nami_core.config import HarnessConfig

    signal_config = HarnessConfig(
        name="signal",
        allowed_agents={"hermes"},
        allowed_actions={"generate_signal", "send_signal"},
        forbid_terms_list=["guarantee", "แน่นอน", "100%", "การันตีกำไร"],
        require_non_empty_fields=["signal", "reason"],
        circuit_breaker_threshold=5,
        budget_guard_max_cost=5.0,
    )

    registry = WorkerRegistry()
    registry.register("signal", signal_worker, config=signal_config)
    registry.register("proxy", proxy_worker)
    registry.register("lottery", lottery_worker)

    # Wire into Hermes
    registry.wire_into_hermes(hermes)

    print(f"Workers: {hermes.list_workers()}")
    print()

    # Dispatch signal
    print("=== Signal Worker ===")
    result = hermes.dispatch("signal", "generate_signal", {"task": "gold_daily"})
    print(f"Output: {result.output}")
    print(f"Quality: {'PASS' if result.passed_quality else 'FAIL'}")
    print()

    # Dispatch proxy
    print("=== Proxy Worker ===")
    result = hermes.dispatch("proxy", "act", {"prompt": "Summarize the report"})
    print(f"Output: {result.output}")
    print()

    # Dispatch lottery
    print("=== Lottery Worker ===")
    result = hermes.dispatch("lottery", "act", {"task": "hanoi_daily"})
    print(f"Output: {result.output}")
    print()

    # Test quality gate — signal with forbidden term
    print("=== Quality Gate Test ===")
    def bad_signal_worker(payload: dict) -> dict:
        return {
            "signal": "XAU/USD Long",
            "reason": "This is a guarantee win 100%",
        }

    hermes.register(
        "bad_signal",
        HarnessRuntime(
            rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"generate_signal"}),
            quality=QualityGate([require_non_empty("signal"), forbid_terms("guarantee", "100%")]),
        ),
        bad_signal_worker,
    )

    try:
        hermes.dispatch("bad_signal", "generate_signal", {})
        print("ERROR: Should have been blocked!")
    except Exception as exc:
        print(f"Blocked by quality gate: {exc}")
        print("Correctly prevented forbidden term from shipping")


if __name__ == "__main__":
    main()
