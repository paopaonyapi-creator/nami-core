"""Tests for v0.5+ workers: notification, analytics, scheduler, cron, email, relay, pipeline."""

from __future__ import annotations

import importlib
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest


def _mod(name: str):
    """Import actual module (not the re-exported function from __init__.py)."""
    return importlib.import_module(f"nami_workers.{name}")


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


# === Notification Worker ===

def test_notification_send_no_subs() -> None:
    m = _mod("notification_worker")
    m._subscribers.clear()
    r = m.notification_worker({"action": "send", "event": "alert", "message": "test"})
    assert r["sent"] == 0

def test_notification_send_telegram() -> None:
    m = _mod("notification_worker")
    m._subscribers.clear()
    m._subscribers["alert"] = [{"type": "telegram", "chat_id": "123"}]
    with patch("nami_workers.utils.telegram_send", return_value={"ok": True}):
        r = m.notification_worker({"action": "send", "event": "alert", "message": "test"})
        assert r["sent"] == 1

def test_notification_send_webhook() -> None:
    m = _mod("notification_worker")
    m._subscribers.clear()
    m._subscribers["alert"] = [{"type": "webhook", "url": "http://example.com/hook"}]
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok":true}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        r = m.notification_worker({"action": "send", "event": "alert", "message": "test"})
        assert r["sent"] == 1

def test_notification_subscribe() -> None:
    m = _mod("notification_worker")
    m._subscribers.clear()
    r = m.notification_worker({"action": "subscribe", "event": "alert", "type": "telegram", "chat_id": "123"})
    assert r["ok"] is True

def test_notification_unsubscribe() -> None:
    m = _mod("notification_worker")
    m._subscribers.clear()
    m._subscribers["alert"] = [{"type": "telegram", "chat_id": "123"}]
    r = m.notification_worker({"action": "unsubscribe", "event": "alert", "chat_id": "123"})
    assert r["ok"] is True and r["removed"] == 1

def test_notification_list() -> None:
    m = _mod("notification_worker")
    m._subscribers.clear()
    assert "subscribers" in m.notification_worker({"action": "list"})

def test_notification_unknown() -> None:
    m = _mod("notification_worker")
    assert "error" in m.notification_worker({"action": "invalid"})


# === Analytics Worker ===

def test_analytics_log() -> None:
    m = _mod("analytics_worker")
    db = _tmp_db(); old = m.DB_PATH; m.DB_PATH = db
    try:
        assert m.analytics_worker({"action": "dispatch_log", "worker": "test", "latency_ms": 50, "ok": True})["logged"] is True
    finally:
        m.DB_PATH = old; os.unlink(db)

def test_analytics_summary() -> None:
    m = _mod("analytics_worker")
    db = _tmp_db(); old = m.DB_PATH; m.DB_PATH = db
    try:
        m.analytics_worker({"action": "dispatch_log", "worker": "test", "latency_ms": 50, "ok": True})
        r = m.analytics_worker({"action": "summary"})
        assert "total" in r and r["total"] >= 1
    finally:
        m.DB_PATH = old; os.unlink(db)

def test_analytics_leaderboard() -> None:
    m = _mod("analytics_worker")
    db = _tmp_db(); old = m.DB_PATH; m.DB_PATH = db
    try:
        m.analytics_worker({"action": "dispatch_log", "worker": "test", "latency_ms": 50, "ok": True})
        assert "leaderboard" in m.analytics_worker({"action": "leaderboard", "limit": 5})
    finally:
        m.DB_PATH = old; os.unlink(db)

def test_analytics_recent() -> None:
    m = _mod("analytics_worker")
    db = _tmp_db(); old = m.DB_PATH; m.DB_PATH = db
    try:
        m.analytics_worker({"action": "dispatch_log", "worker": "test", "latency_ms": 50, "ok": True})
        assert "recent" in m.analytics_worker({"action": "recent", "limit": 5})
    finally:
        m.DB_PATH = old; os.unlink(db)

def test_analytics_unknown() -> None:
    m = _mod("analytics_worker")
    assert "error" in m.analytics_worker({"action": "invalid"})


# === Scheduler Worker ===

def test_scheduler_list() -> None:
    m = _mod("scheduler_worker")
    mock_s = MagicMock(); mock_s.status.return_value = {"jobs": [], "running": True}
    m.set_scheduler_ref(mock_s)
    assert "jobs" in m.scheduler_worker({"action": "list"})

def test_scheduler_run_now_no_key() -> None:
    m = _mod("scheduler_worker")
    m.set_scheduler_ref(MagicMock())
    assert "error" in m.scheduler_worker({"action": "run_now", "job": ""})

def test_scheduler_run_now_not_found() -> None:
    m = _mod("scheduler_worker")
    mock_s = MagicMock(); mock_s.hermes = MagicMock()
    m.set_scheduler_ref(mock_s)
    assert "error" in m.scheduler_worker({"action": "run_now", "job": "no:such"})

def test_scheduler_enable() -> None:
    m = _mod("scheduler_worker")
    m.set_scheduler_ref(MagicMock())
    assert m.scheduler_worker({"action": "enable"})["ok"] is True

def test_scheduler_disable() -> None:
    m = _mod("scheduler_worker")
    m.set_scheduler_ref(MagicMock())
    assert m.scheduler_worker({"action": "disable"})["ok"] is True

def test_scheduler_no_ref() -> None:
    m = _mod("scheduler_worker")
    m.set_scheduler_ref(None)
    assert "error" in m.scheduler_worker({"action": "list"})

def test_scheduler_unknown() -> None:
    m = _mod("scheduler_worker")
    m.set_scheduler_ref(MagicMock())
    assert "error" in m.scheduler_worker({"action": "invalid"})


# === Cron Worker ===

def test_cron_schedule() -> None:
    m = _mod("cron_worker")
    db = _tmp_db(); old = m.CRON_DB; m.CRON_DB = db
    try:
        r = m.cron_worker({"action": "schedule", "worker": "default", "cron_action": "echo", "run_at": "2099-01-01T00:00:00", "job_payload": {}})
        assert r["ok"] is True and "job_id" in r
    finally:
        m.CRON_DB = old; os.unlink(db)

def test_cron_list() -> None:
    m = _mod("cron_worker")
    db = _tmp_db(); old = m.CRON_DB; m.CRON_DB = db
    try:
        m.cron_worker({"action": "schedule", "worker": "default", "cron_action": "echo", "run_at": "2099-01-01T00:00:00", "job_payload": {}})
        assert "jobs" in m.cron_worker({"action": "list", "status": "pending"})
    finally:
        m.CRON_DB = old; os.unlink(db)

def test_cron_cancel() -> None:
    m = _mod("cron_worker")
    db = _tmp_db(); old = m.CRON_DB; m.CRON_DB = db
    try:
        s = m.cron_worker({"action": "schedule", "worker": "default", "cron_action": "echo", "run_at": "2099-01-01T00:00:00", "job_payload": {}})
        assert m.cron_worker({"action": "cancel", "job_id": s["job_id"]})["ok"] is True
    finally:
        m.CRON_DB = old; os.unlink(db)

def test_cron_unknown() -> None:
    m = _mod("cron_worker")
    assert "error" in m.cron_worker({"action": "invalid"})


# === Email Worker ===

def test_email_send_no_smtp() -> None:
    m = _mod("email_worker")
    os.environ.pop("NAMI_SMTP_USER", None)
    assert "error" in m.email_worker({"action": "send", "to": "t@t.com", "subject": "s", "body": "b"})

def test_email_send_no_to() -> None:
    m = _mod("email_worker")
    assert "error" in m.email_worker({"action": "send", "to": ""})

def test_email_batch_no_recipients() -> None:
    m = _mod("email_worker")
    assert "error" in m.email_worker({"action": "batch", "recipients": []})

def test_email_templates() -> None:
    m = _mod("email_worker")
    r = m.email_worker({"action": "templates"})
    assert "templates" in r and len(r["templates"]) > 0

def test_email_unknown() -> None:
    m = _mod("email_worker")
    assert "error" in m.email_worker({"action": "invalid"})


# === Relay Worker ===

def test_relay_register() -> None:
    m = _mod("relay_worker")
    db = _tmp_db(); old = m.RELAY_DB; m.RELAY_DB = db
    try:
        r = m.relay_worker({"action": "register", "url": "http://example.com/hook", "event": "dispatch"})
        assert r["ok"] is True and "hook_id" in r
    finally:
        m.RELAY_DB = old; os.unlink(db)

def test_relay_register_no_url() -> None:
    m = _mod("relay_worker")
    assert "error" in m.relay_worker({"action": "register", "url": ""})

def test_relay_list() -> None:
    m = _mod("relay_worker")
    db = _tmp_db(); old = m.RELAY_DB; m.RELAY_DB = db
    try:
        m.relay_worker({"action": "register", "url": "http://example.com/hook", "event": "dispatch"})
        r = m.relay_worker({"action": "list"})
        assert "hooks" in r and len(r["hooks"]) > 0
    finally:
        m.RELAY_DB = old; os.unlink(db)

def test_relay_unregister() -> None:
    m = _mod("relay_worker")
    db = _tmp_db(); old = m.RELAY_DB; m.RELAY_DB = db
    try:
        reg = m.relay_worker({"action": "register", "url": "http://example.com/hook", "event": "dispatch"})
        assert m.relay_worker({"action": "unregister", "hook_id": reg["hook_id"]})["ok"] is True
    finally:
        m.RELAY_DB = old; os.unlink(db)

def test_relay_trigger_no_hooks() -> None:
    m = _mod("relay_worker")
    db = _tmp_db(); old = m.RELAY_DB; m.RELAY_DB = db
    try:
        r = m.relay_worker({"action": "trigger", "event": "nonexistent", "data": {}})
        assert r["ok"] is True and r["fired"] == 0
    finally:
        m.RELAY_DB = old; os.unlink(db)

def test_relay_unknown() -> None:
    m = _mod("relay_worker")
    assert "error" in m.relay_worker({"action": "invalid"})


# === Pipeline Worker ===

def test_pipeline_transform_rename() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "transform", "data": {"old": 1, "keep": 2}, "steps": [{"op": "rename", "field": "old", "value": "new"}]})
    assert r["ok"] and "new" in r["result"] and "old" not in r["result"]

def test_pipeline_transform_filter() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "transform", "data": {"a": 1, "b": 2}, "steps": [{"op": "filter", "field": "b"}]})
    assert r["ok"] and "b" not in r["result"]

def test_pipeline_transform_add() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "transform", "data": {"a": 1}, "steps": [{"op": "add", "field": "b", "value": 2}]})
    assert r["ok"] and r["result"]["b"] == 2

def test_pipeline_transform_select() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "transform", "data": {"a": 1, "b": 2, "c": 3}, "steps": [{"op": "select", "field": "", "value": ["a", "b"]}]})
    assert r["ok"] and set(r["result"].keys()) == {"a", "b"}

def test_pipeline_transform_flatten() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "transform", "data": {"outer": {"inner": 1}, "flat": 2}, "steps": [{"op": "flatten"}]})
    assert r["ok"] and "outer.inner" in r["result"]

def test_pipeline_transform_no_steps() -> None:
    m = _mod("pipeline_worker")
    assert "error" in m.pipeline_worker({"action": "transform", "data": {}, "steps": []})

def test_pipeline_aggregate_sum() -> None:
    m = _mod("pipeline_worker")
    assert m.pipeline_worker({"action": "aggregate", "data": [1, 2, 3, 4], "operation": "sum"})["result"] == 10

def test_pipeline_aggregate_avg() -> None:
    m = _mod("pipeline_worker")
    assert m.pipeline_worker({"action": "aggregate", "data": [10, 20, 30], "operation": "avg"})["result"] == 20.0

def test_pipeline_aggregate_min_max() -> None:
    m = _mod("pipeline_worker")
    assert m.pipeline_worker({"action": "aggregate", "data": [5, 1, 9], "operation": "min"})["result"] == 1
    assert m.pipeline_worker({"action": "aggregate", "data": [5, 1, 9], "operation": "max"})["result"] == 9

def test_pipeline_aggregate_count() -> None:
    m = _mod("pipeline_worker")
    assert m.pipeline_worker({"action": "aggregate", "data": [1, 2, 3], "operation": "count"})["result"] == 3

def test_pipeline_aggregate_median() -> None:
    m = _mod("pipeline_worker")
    assert m.pipeline_worker({"action": "aggregate", "data": [1, 3, 5], "operation": "median"})["result"] == 3

def test_pipeline_aggregate_field() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "aggregate", "data": [{"price": 10}, {"price": 20}, {"price": 30}], "operation": "sum", "field": "price"})
    assert r["result"] == 60

def test_pipeline_aggregate_empty() -> None:
    m = _mod("pipeline_worker")
    assert "error" in m.pipeline_worker({"action": "aggregate", "data": [], "operation": "sum"})

def test_pipeline_export_json() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "export", "data": {"key": "val"}, "format": "json"})
    assert r["ok"] and '"key"' in r["output"]

def test_pipeline_export_csv() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "export", "data": [{"name": "a", "val": 1}, {"name": "b", "val": 2}], "format": "csv"})
    assert r["ok"] and "name,val" in r["output"]

def test_pipeline_export_summary() -> None:
    m = _mod("pipeline_worker")
    r = m.pipeline_worker({"action": "export", "data": {"a": 1, "b": 2}, "format": "summary"})
    assert r["ok"] and "keys" in r["output"]

def test_pipeline_unknown() -> None:
    m = _mod("pipeline_worker")
    assert "error" in m.pipeline_worker({"action": "invalid"})
