from __future__ import annotations

from nami_core.runtime.queue.worker import main


def test_worker_dry_run_reports_ready(monkeypatch, capsys):
    monkeypatch.setenv("NAMI_WORKER", "status")
    main(["--dry-run"])
    captured = capsys.readouterr()
    assert "worker ready" in captured.out
