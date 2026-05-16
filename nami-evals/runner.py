from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import yaml

EVAL_ROOT = Path(__file__).resolve().parent
if str(EVAL_ROOT) not in sys.path:
    sys.path.insert(0, str(EVAL_ROOT))

SUITES_DIR = EVAL_ROOT / "suites"
BASELINES_DIR = EVAL_ROOT / "baselines"
RESULTS_DIR = EVAL_ROOT / "results"


@dataclass(frozen=True)
class CaseResult:
    suite: str
    case_id: str
    score: float
    passed: bool
    reason: str
    elapsed_ms: int
    actual: Any
    expected: Any


def _suite_name(value: str) -> str:
    return value.replace("-", "_")


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"suite must be a mapping: {path}")
    return data


def _load_baseline(suite_name: str, baselines_dir: Path) -> dict[str, Any]:
    path = baselines_dir / f"{suite_name}.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    cases = data.get("cases")
    if not isinstance(cases, dict):
        raise ValueError(f"baseline cases must be a mapping: {path}")
    return data


def _load_judge(name: str):
    module_name = name.replace("-", "_")
    return importlib.import_module(f"judges.{module_name}")


def _actual_output(case: dict[str, Any]) -> Any:
    if "current_output" not in case:
        raise ValueError(f"case missing current_output: {case.get('id')}")
    return case["current_output"]


async def _run_case(suite_name: str, case: dict[str, Any], baseline_cases: dict[str, Any]) -> CaseResult:
    started = time.monotonic()
    case_id = str(case.get("id") or "")
    if not case_id:
        raise ValueError("case missing id")
    if case_id not in baseline_cases:
        raise ValueError(f"baseline missing case: {case_id}")
    judge_name = str(case.get("judge") or "exact_match")
    judge = _load_judge(judge_name)
    actual = _actual_output(case)
    expected = baseline_cases[case_id]
    result = await asyncio.to_thread(judge.score, actual, expected, case)
    score = float(result.get("score", 0.0))
    threshold = float(case.get("threshold", 1.0))
    passed = bool(result.get("passed", score >= threshold)) and score >= threshold
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return CaseResult(
        suite=suite_name,
        case_id=case_id,
        score=score,
        passed=passed,
        reason=str(result.get("reason") or ""),
        elapsed_ms=elapsed_ms,
        actual=actual,
        expected=expected,
    )


def _write_junit(suite_name: str, results: list[CaseResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = [result for result in results if not result.passed]
    suite = ElementTree.Element(
        "testsuite",
        {
            "name": suite_name,
            "tests": str(len(results)),
            "failures": str(len(failures)),
            "time": str(round(sum(result.elapsed_ms for result in results) / 1000.0, 3)),
        },
    )
    for result in results:
        case = ElementTree.SubElement(
            suite,
            "testcase",
            {
                "classname": suite_name,
                "name": result.case_id,
                "time": str(round(result.elapsed_ms / 1000.0, 3)),
            },
        )
        if not result.passed:
            failure = ElementTree.SubElement(case, "failure", {"message": result.reason or "eval failed"})
            failure.text = json.dumps({"score": result.score, "actual": result.actual, "expected": result.expected}, ensure_ascii=False, default=str)
    path = output_dir / f"{suite_name}.xml"
    ElementTree.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return path


async def run_suite(suite_name: str, *, fail_under: float, baselines_dir: Path, results_dir: Path) -> tuple[bool, float, list[CaseResult], Path]:
    normalized = _suite_name(suite_name)
    suite_path = SUITES_DIR / f"{normalized}.yaml"
    suite = _load_yaml(suite_path)
    baseline = _load_baseline(normalized, baselines_dir)
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"suite has no cases: {suite_path}")
    results = await asyncio.gather(*[_run_case(normalized, case, baseline["cases"]) for case in cases])
    score = sum(result.score for result in results) / len(results)
    junit_path = _write_junit(normalized, list(results), results_dir)
    passed = score >= fail_under and all(result.passed for result in results)
    return passed, score, list(results), junit_path


def _all_suite_names() -> list[str]:
    return sorted(path.stem for path in SUITES_DIR.glob("*.yaml"))


async def run_command(args: argparse.Namespace) -> int:
    baselines_dir = Path(args.baselines_dir or os.environ.get("NAMI_EVALS_BASELINES_DIR") or BASELINES_DIR)
    results_dir = Path(args.results_dir or os.environ.get("NAMI_EVALS_RESULTS_DIR") or RESULTS_DIR)
    suite_names = _all_suite_names() if args.all else [_suite_name(args.suite)]
    exit_code = 0
    for suite_name in suite_names:
        passed, score, results, junit_path = await run_suite(suite_name, fail_under=args.fail_under, baselines_dir=baselines_dir, results_dir=results_dir)
        failed = len([result for result in results if not result.passed])
        print(f"{suite_name}: score={score:.3f} cases={len(results)} failed={failed} junit={junit_path}")
        if not passed:
            exit_code = 1
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nami-evals")
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run")
    run.add_argument("suite", nargs="?")
    run.add_argument("--all", action="store_true")
    run.add_argument("--fail-under", type=float, default=0.85)
    run.add_argument("--baselines-dir")
    run.add_argument("--results-dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        if not args.all and not args.suite:
            parser.error("run requires <suite> unless --all is set")
        return asyncio.run(run_command(args))
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
