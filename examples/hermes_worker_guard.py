from nami_harness.brakes import CircuitBreaker, FileKillSwitch
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy
from nami_harness.runtime import HarnessContext, HarnessRuntime
from nami_harness.sensors import JsonlSensor


def hermes_worker(payload: dict) -> dict:
    return {"answer": f"Hermes processed: {payload['task']}"}


runtime = HarnessRuntime(
    rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"summarize", "draft"}, max_daily_actions=100),
    quality=QualityGate([require_non_empty("answer"), forbid_terms("raw_secret", "api_key=")]),
    sensor=JsonlSensor(".nami-harness/events.jsonl"),
    kill_switch=FileKillSwitch(".kill"),
    circuit_breaker=CircuitBreaker(failure_threshold=3),
)

result = runtime.run(
    HarnessContext(agent="hermes", action="summarize"),
    {"task": "summarize the service health report"},
    hermes_worker,
)

print(result.output["answer"])
