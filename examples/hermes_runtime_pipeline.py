from nami_harness.brakes import BudgetGuard, CircuitBreaker, FileKillSwitch
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy, RateLimitRail
from nami_harness.runtime import HarnessContext, HarnessRuntime
from nami_harness.sensors import JsonlSensor


def hermes_router(payload: dict) -> dict:
    task = payload["task"]
    return {"answer": f"Hermes routed and completed: {task}"}


runtime = HarnessRuntime(
    rails=RailPolicy(
        allowed_agents={"hermes"},
        allowed_actions={"summarize", "draft"},
        max_daily_actions=100,
        rate_limit=RateLimitRail(max_events=10, window_seconds=60),
    ),
    quality=QualityGate([require_non_empty("answer"), forbid_terms("raw_secret", "api_key=")]),
    sensor=JsonlSensor(".nami-harness/hermes-runtime-events.jsonl"),
    kill_switch=FileKillSwitch(".kill"),
    circuit_breaker=CircuitBreaker(failure_threshold=3),
    budget_guard=BudgetGuard(max_cost=1.0),
)

result = runtime.run(
    HarnessContext(agent="hermes", action="summarize", estimated_cost=0.05),
    {"task": "summarize the agent health report"},
    hermes_router,
)

print(result.output["answer"])
