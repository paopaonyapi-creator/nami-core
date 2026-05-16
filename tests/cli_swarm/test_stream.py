"""Phase 32 — stream publisher tests."""

from __future__ import annotations

from nami_core.cli_swarm.stream import InMemoryPublisher, make_event


def test_publish_records_event() -> None:
    pub = InMemoryPublisher()
    pub.publish("nami:cli:s1", make_event("s1", "stdout", "hello", timestamp=1.0))
    assert pub.streams["nami:cli:s1"][0]["body"] == "hello"
    assert pub.streams["nami:cli:s1"][0]["ts"] == 1.0


def test_publish_multiple_appends_in_order() -> None:
    pub = InMemoryPublisher()
    for i in range(3):
        pub.publish("s", make_event("s", "stdout", f"line{i}", timestamp=float(i)))
    assert [e["body"] for e in pub.streams["s"]] == ["line0", "line1", "line2"]


def test_trim_caps_stream_length() -> None:
    pub = InMemoryPublisher()
    for i in range(10):
        pub.publish("s", make_event("s", "stdout", str(i), timestamp=float(i)))
    pub.trim("s", maxlen=3)
    assert [e["body"] for e in pub.streams["s"]] == ["7", "8", "9"]


def test_trim_below_cap_noop() -> None:
    pub = InMemoryPublisher()
    pub.publish("s", make_event("s", "stdout", "a", timestamp=1.0))
    pub.trim("s", maxlen=10)
    assert len(pub.streams["s"]) == 1


def test_make_event_default_timestamp_present() -> None:
    ev = make_event("s1", "lifecycle", "started")
    assert ev["session_id"] == "s1"
    assert ev["kind"] == "lifecycle"
    assert isinstance(ev["ts"], float)
