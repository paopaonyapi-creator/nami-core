import json

from nami_harness.sensors import JsonlSensor


def test_jsonl_sensor_records_event(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    sensor = JsonlSensor(path)

    event = sensor.record("task.completed", {"agent": "hermes"})

    line = path.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["event_id"] == event.event_id
    assert record["event_type"] == "task.completed"
    assert record["payload"] == {"agent": "hermes"}


def test_jsonl_sensor_records_stable_schema_fields(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    sensor = JsonlSensor(path)

    sensor.record(
        "task.completed",
        {"output_keys": ["answer"]},
        status="success",
        agent="hermes",
        action="summarize",
        correlation_id="trace-1",
        metadata={"safe": True},
    )

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["schema_version"] == "1.0"
    assert record["status"] == "success"
    assert record["agent"] == "hermes"
    assert record["action"] == "summarize"
    assert record["correlation_id"] == "trace-1"
    assert record["metadata"] == {"safe": True}


def test_jsonl_sensor_swallows_oserror(tmp_path, caplog):
    """Sensor writes must never crash the dispatch path on permission errors."""
    import logging
    from nami_harness.sensors import JsonlSensor, _warned_paths

    bad = tmp_path / "blocker"
    bad.write_text("not a directory")
    sensor = JsonlSensor(bad / "events.jsonl")

    _warned_paths.clear()
    with caplog.at_level(logging.WARNING, logger="nami_harness.sensors"):
        event = sensor.record("test", {"a": 1})
        sensor.record("test", {"a": 2})

    assert event.event_type == "test"
    assert sum(1 for r in caplog.records if "sensor write failed" in r.message) == 1

