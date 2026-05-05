import pytest

from nami_harness.exceptions import QualityGateFailed
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty


def test_quality_gate_passes_valid_payload() -> None:
    gate = QualityGate([require_non_empty("answer"), forbid_terms("secret")])

    gate.assert_passes({"answer": "safe output"})


def test_quality_gate_fails_empty_required_field() -> None:
    gate = QualityGate([require_non_empty("answer")])

    with pytest.raises(QualityGateFailed):
        gate.assert_passes({"answer": ""})


def test_quality_gate_fails_forbidden_term() -> None:
    gate = QualityGate([forbid_terms("secret")])

    with pytest.raises(QualityGateFailed):
        gate.assert_passes({"answer": "do not leak secret values"})
