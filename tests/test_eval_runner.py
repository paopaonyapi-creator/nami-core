from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "nami-evals" / "runner.py"


def test_eval_runner_chat_quality_passes(tmp_path):
    result = subprocess.run(
        [sys.executable, str(RUNNER), "run", "chat_quality", "--fail-under", "0.85", "--results-dir", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "chat_quality: score=1.000" in result.stdout
    junit = tmp_path / "chat_quality.xml"
    assert junit.exists()
    suite = ElementTree.parse(junit).getroot()
    assert suite.attrib["tests"] == "10"
    assert suite.attrib["failures"] == "0"


def test_eval_runner_baseline_mutation_fails_and_writes_junit(tmp_path):
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    for path in (ROOT / "nami-evals" / "baselines").glob("*.json"):
        (baselines / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    baseline_path = baselines / "tool_invocation.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["cases"]["ti_runtime_tool_shape"]["endpoint"] = "/wrong"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(RUNNER), "run", "tool_invocation", "--fail-under", "0.85", "--baselines-dir", str(baselines), "--results-dir", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    junit = tmp_path / "tool_invocation.xml"
    suite = ElementTree.parse(junit).getroot()
    assert suite.attrib["failures"] == "1"
    failure = suite.find("testcase/failure")
    assert failure is not None
    assert "ti_runtime_tool_shape" in ElementTree.tostring(suite, encoding="unicode")


def test_all_eval_suites_have_committed_baselines():
    suite_names = {path.stem for path in (ROOT / "nami-evals" / "suites").glob("*.yaml")}
    baseline_names = {path.stem for path in (ROOT / "nami-evals" / "baselines").glob("*.json")}

    assert suite_names == {"chat_quality", "lottery_correctness", "tool_invocation", "safety_suite"}
    assert baseline_names == suite_names

    expected_counts = {"chat_quality": 10, "lottery_correctness": 5, "tool_invocation": 5, "safety_suite": 26}
    for suite_name in suite_names:
        suite = yaml.safe_load((ROOT / "nami-evals" / "suites" / f"{suite_name}.yaml").read_text(encoding="utf-8"))
        baseline = json.loads((ROOT / "nami-evals" / "baselines" / f"{suite_name}.json").read_text(encoding="utf-8"))
        cases = {case["id"] for case in suite["cases"]}
        assert len(cases) == expected_counts[suite_name]
        assert set(baseline["cases"]) == cases


def test_deploy_script_contains_eval_gate_and_break_glass():
    script = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert "python nami-evals/runner.py run --all --fail-under" in script
    assert "SKIP_EVAL" in script
    assert "incidents.md" in script
    assert "NAMI_DEPLOY_DRY_RUN" in script
