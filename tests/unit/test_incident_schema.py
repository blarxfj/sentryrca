"""Tests for IncidentCase and EvalCase Pydantic schemas."""

import pytest
from pydantic import ValidationError

from sentryrca.schema.eval import EvalCase
from sentryrca.schema.incident import DeployEntry, IncidentCase

# ─── Fixtures ────────────────────────────────────────────────────────────────


def _deploy(sha: str = "abc123def456") -> DeployEntry:
    return DeployEntry(
        sha=sha,
        timestamp="2024-01-15T02:30:00Z",
        author="Jane Doe",
        message="feat: add order history pagination",
        changed_files=["src/checkout/order.go"],
    )


def _deploys(n: int = 5) -> list[DeployEntry]:
    return [_deploy(sha=f"sha{i:010d}") for i in range(n)]


def _valid_incident(**overrides: object) -> IncidentCase:
    defaults: dict[str, object] = {
        "id": "syn-001",
        "subset": "synthetic",
        "category": "db_saturation",
        "affected_service": "checkout-service",
        "severity": "high",
        "alert_text": "checkout-service p99 latency > 5s for 3 consecutive minutes",
        "log_window": "2024-01-15T03:41:22Z INFO checkout-service\n" * 10,
        "recent_deploys": _deploys(5),
        "ground_truth_root_cause": "N+1 query introduced in sha0000000000",
        "ground_truth_remediation": "Roll back to previous version",
    }
    defaults.update(overrides)
    return IncidentCase.model_validate(defaults)


# ─── IncidentCase tests ───────────────────────────────────────────────────────


def test_valid_round_trip() -> None:
    incident = _valid_incident()
    restored = IncidentCase.model_validate_json(incident.model_dump_json())
    assert restored == incident


def test_missing_required_field_rejected() -> None:
    with pytest.raises(ValidationError):
        IncidentCase.model_validate(
            {
                "id": "syn-001",
                "subset": "synthetic",
                # alert_text intentionally missing
                "category": "db_saturation",
                "affected_service": "checkout-service",
                "severity": "high",
                "log_window": "x" * 100,
                "recent_deploys": _deploys(5),
                "ground_truth_root_cause": "cause",
                "ground_truth_remediation": "fix",
            }
        )


def test_invalid_subset_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_incident(subset="unknown")


def test_invalid_category_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_incident(category="random_category")


def test_invalid_id_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_incident(id="incident-001")  # must be syn/real/adv-NNN


def test_red_herring_defaults_to_none_for_synthetic() -> None:
    incident = _valid_incident(subset="synthetic")
    assert incident.red_herring is None


def test_adversarial_requires_red_herring() -> None:
    with pytest.raises(ValidationError, match="red_herring"):
        _valid_incident(id="adv-001", subset="adversarial", red_herring=None)


def test_adversarial_with_red_herring_valid() -> None:
    incident = _valid_incident(
        id="adv-001",
        subset="adversarial",
        red_herring="The nginx deploy touched rate-limit config but the real cause is cert expiry.",
    )
    assert incident.subset == "adversarial"
    assert incident.red_herring is not None


def test_non_adversarial_rejects_red_herring() -> None:
    with pytest.raises(ValidationError, match="red_herring"):
        _valid_incident(subset="synthetic", red_herring="some hint")


def test_recent_deploys_min_length_enforced() -> None:
    with pytest.raises(ValidationError):
        _valid_incident(recent_deploys=_deploys(4))  # minimum is 5


def test_recent_deploys_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        _valid_incident(recent_deploys=_deploys(11))  # maximum is 10


def test_log_window_min_length_enforced() -> None:
    with pytest.raises(ValidationError):
        _valid_incident(log_window="too short")


# ─── DeployEntry tests ────────────────────────────────────────────────────────


def test_deploy_entry_valid_round_trip() -> None:
    d = _deploy()
    assert DeployEntry.model_validate_json(d.model_dump_json()) == d


def test_deploy_entry_sha_min_length() -> None:
    with pytest.raises(ValidationError):
        DeployEntry(
            sha="abc",  # too short (min 7)
            timestamp="2024-01-15T02:30:00Z",
            author="Jane",
            message="feat: x",
        )


def test_deploy_entry_invalid_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        DeployEntry(
            sha="abc1234567",
            timestamp="20240115T02:30:00Z",  # missing dashes in date part
            author="Jane",
            message="feat: x",
        )


def test_deploy_entry_changed_files_defaults_to_empty() -> None:
    d = DeployEntry(
        sha="abc1234567",
        timestamp="2024-01-15T02:30:00Z",
        author="Jane",
        message="feat: x",
    )
    assert d.changed_files == []


# ─── EvalCase tests ───────────────────────────────────────────────────────────


def test_eval_case_round_trip() -> None:
    ec = EvalCase(
        incident=_valid_incident(),
        expected_top_hypothesis="N+1 query in order history endpoint",
        expected_affected_service="checkout-service",
    )
    restored = EvalCase.model_validate_json(ec.model_dump_json())
    assert restored == ec


def test_eval_case_human_validated_defaults_false() -> None:
    ec = EvalCase(
        incident=_valid_incident(),
        expected_top_hypothesis="hypothesis",
        expected_affected_service="checkout-service",
    )
    assert ec.human_validated is False
    assert ec.human_notes is None
