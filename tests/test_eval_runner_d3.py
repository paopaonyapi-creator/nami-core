"""Tests for D3 wiring in nami-evals runner.

The runner threads each (suite, judge) pair through EvaluatorAcceptanceTracker.
Below the D3 100-sample window the tracker stays silent. With a synthetic
suite of 100 always-passing cases, D3 fires and prints a `[safety] D3 alert`
line + bumps nami_safety_detection_total{pattern=D3,action=alert}.

Tests construct synthetic suites in tmp_path (no edits to committed suites).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "nami-evals" / "runner.py"


def _build_synthetic_suite(tmp_path: Path, *, name: str, cases: list[dict], baseline_cases: dict) -> tuple[Path, Path]:
    """Stage a fresh suite/baseline pair under tmp_path/* so the runner can
    pick it up via --suites-dir + --baselines-dir overrides.
    """
    suites_dir = tmp_path / "suites"
    baselines_dir = tmp_path / "baselines"
    suites_dir.mkdir(parents=True)
    baselines_dir.mkdir(parents=True)
    (suites_dir / f"{name}.yaml").write_text(yaml.safe_dump({"suite": name, "cases": cases}), encoding="utf-8")
    (baselines_dir / f"{name}.json").write_text(json.dumps({"suite": name, "cases": baseline_cases}), encoding="utf-8")
    return suites_dir, baselines_dir


def _run(suites_dir: Path, baselines_dir: Path, results_dir: Path, suite_name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), "run", suite_name, "--fail-under", "0.99",
         "--suites-dir", str(suites_dir),
         "--baselines-dir", str(baselines_dir),
         "--results-dir", str(results_dir)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_d3_silent_below_window(tmp_path: Path) -> None:
    """50 always-passing cases stays silent (below 100-sample window)."""
    cases = []
    baseline = {}
    for i in range(50):
        cid = f"c{i:03d}"
        cases.append({
            "id": cid,
            "judge": "exact_match",
            "threshold": 1.0,
            "current_output": "x",
        })
        baseline[cid] = "x"
    suites_dir, baselines_dir = _build_synthetic_suite(
        tmp_path, name="suite_small", cases=cases, baseline_cases=baseline
    )
    result = _run(suites_dir, baselines_dir, tmp_path / "results", "suite_small")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[safety] D3 alert" not in result.stdout


def test_d3_fires_on_100pct_acceptance_over_100_cases(tmp_path: Path) -> None:
    """100 cases × always-pass judge → D3 must alert with rate=100%."""
    cases = []
    baseline = {}
    for i in range(100):
        cid = f"c{i:03d}"
        cases.append({
            "id": cid,
            "judge": "exact_match",
            "threshold": 1.0,
            "current_output": "x",
        })
        baseline[cid] = "x"
    suites_dir, baselines_dir = _build_synthetic_suite(
        tmp_path, name="suite_collude", cases=cases, baseline_cases=baseline
    )
    result = _run(suites_dir, baselines_dir, tmp_path / "results", "suite_collude")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[safety] D3 alert" in result.stdout
    assert "judge='exact_match'" in result.stdout
    assert "rate=100.00%" in result.stdout


def test_d3_silent_when_acceptance_below_threshold(tmp_path: Path) -> None:
    """100 cases, 5 fail (95% acceptance) → D3 must stay silent (>0.99 threshold)."""
    cases = []
    baseline = {}
    for i in range(100):
        cid = f"c{i:03d}"
        # First 5 cases: actual != expected → judge returns passed=False.
        actual = "x" if i >= 5 else "wrong"
        cases.append({
            "id": cid,
            "judge": "exact_match",
            "threshold": 1.0,
            "current_output": actual,
        })
        baseline[cid] = "x"
    suites_dir, baselines_dir = _build_synthetic_suite(
        tmp_path, name="suite_mixed", cases=cases, baseline_cases=baseline
    )
    result = _run(suites_dir, baselines_dir, tmp_path / "results", "suite_mixed")
    # returncode != 0 is fine — fail-under triggers because 5 cases failed.
    # We only care about the safety line.
    assert "[safety] D3 alert" not in result.stdout
