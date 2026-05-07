"""Tests for the 5 external-service wrapper workers (v0.15.0).

These workers wrap standalone systemd services on the VPS:
  - clipboardbypao (port 3001)
  - hanoi_stats (port 3002)
  - laopatana_lab (port 3000)
  - miroshark_oracle (port 8003, FastAPI)
  - open_design (port 7456)

Tests use monkeypatch to fake urllib.request and subprocess so they run
hermetically without needing the actual services up.
"""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from nami_workers.clipboardbypao_worker import clipboardbypao_worker
from nami_workers.hanoi_stats_worker import hanoi_stats_worker
from nami_workers.laopatana_lab_worker import laopatana_lab_worker
from nami_workers.open_design_worker import open_design_worker
from nami_workers.miroshark_oracle_worker import miroshark_oracle_worker


class _FakeResp:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n: int = -1):
        if n == -1:
            return self._body
        return self._body[:n]


def _patch_urlopen(module_path: str, status: int = 200, body: bytes = b'{"ok":true}'):
    return patch(f"{module_path}.urllib.request.urlopen", return_value=_FakeResp(status, body))


def _patch_subprocess(module_path: str, returncode: int = 0, stdout: str = "active\n"):
    fake = MagicMock(stdout=stdout, returncode=returncode)
    return patch(f"{module_path}.subprocess.run", return_value=fake)


@pytest.mark.parametrize("worker,module", [
    (clipboardbypao_worker, "nami_workers.clipboardbypao_worker"),
    (hanoi_stats_worker, "nami_workers.hanoi_stats_worker"),
    (laopatana_lab_worker, "nami_workers.laopatana_lab_worker"),
    (open_design_worker, "nami_workers.open_design_worker"),
])
def test_simple_worker_status_active(worker, module):
    with _patch_urlopen(module), _patch_subprocess(module):
        out = worker({"action": "status"})
    assert out["healthy"] is True
    assert out["systemd"] == "active"
    assert out["http_ok"] is True


@pytest.mark.parametrize("worker,module", [
    (clipboardbypao_worker, "nami_workers.clipboardbypao_worker"),
    (hanoi_stats_worker, "nami_workers.hanoi_stats_worker"),
])
def test_simple_worker_status_unreachable(worker, module):
    """When HTTP probe fails the worker reports unhealthy without raising."""
    import urllib.error
    with patch(f"{module}.urllib.request.urlopen", side_effect=urllib.error.URLError("conn refused")), \
         _patch_subprocess(module, stdout="inactive\n"):
        out = worker({"action": "status"})
    assert out["healthy"] is False
    assert out["http_ok"] is False
    assert out["systemd"] == "inactive"


@pytest.mark.parametrize("worker", [clipboardbypao_worker, hanoi_stats_worker, laopatana_lab_worker, open_design_worker])
def test_simple_worker_unknown_action(worker):
    out = worker({"action": "nope"})
    assert "error" in out


def test_miroshark_oracle_status():
    with _patch_urlopen("nami_workers.miroshark_oracle_worker"), \
         _patch_subprocess("nami_workers.miroshark_oracle_worker"):
        out = miroshark_oracle_worker({"action": "status"})
    assert out["healthy"] is True
    assert "/oracle/analyze" in out["endpoints"]


def test_miroshark_oracle_ai_analyze_proxies_post():
    body_resp = json.dumps({"signal": "long", "confidence": 0.7}).encode()
    with patch("nami_workers.miroshark_oracle_worker.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _FakeResp(200, body_resp)
        out = miroshark_oracle_worker({"action": "ai_analyze", "body": {"symbol": "XAUUSD"}})
    assert out["ok"] is True
    assert out["data"]["signal"] == "long"
    # Verify it was a POST request
    assert mock_urlopen.call_args[0][0].method == "POST"


def test_miroshark_oracle_unknown_action():
    out = miroshark_oracle_worker({"action": "bogus"})
    assert "error" in out
