"""Unit tests for the incident chunker — no DB or network required."""

import pytest

from sentryrca.retrieval.chunker import _LOG_LINES_PER_CHUNK, chunk_incident
from sentryrca.schema.incident import DeployEntry, IncidentCase


def _deploy(sha: str = "abc123def456abc") -> DeployEntry:
    return DeployEntry(
        sha=sha,
        timestamp="2024-01-15T02:30:00Z",
        author="dev",
        message="fix: patch something",
        changed_files=["src/main.go"],
    )


def _unique_deploys(n: int = 5) -> list[DeployEntry]:
    # SHAs differ in their first chars so chunk IDs are unique after [:12] truncation.
    return [_deploy(sha=f"{i:07d}abcdef0") for i in range(n)]


def _incident(**overrides: object) -> IncidentCase:
    defaults: dict[str, object] = {
        "id": "syn-001",
        "subset": "synthetic",
        "category": "db_saturation",
        "affected_service": "checkout-service",
        "severity": "high",
        "alert_text": "ALERT: checkout-service p99 > 5s for 5 consecutive minutes",
        "log_window": "\n".join(
            [f"2024-01-15T03:4{i:01}:00Z INFO log line {i}" for i in range(60)]
        ),
        "recent_deploys": _unique_deploys(5),
        "ground_truth_root_cause": "N+1 query in order finalisation",
        "ground_truth_remediation": "Roll back sha",
    }
    defaults.update(overrides)
    return IncidentCase.model_validate(defaults)


def test_alert_chunk_produced() -> None:
    inc = _incident()
    chunks = chunk_incident(inc)
    alert_chunks = [c for c in chunks if c.chunk_type == "alert"]
    assert len(alert_chunks) == 1
    assert alert_chunks[0].content == inc.alert_text
    assert alert_chunks[0].id == "syn-001_alert_0"


def test_log_chunks_cover_all_lines() -> None:
    n_lines = 60
    inc = _incident(log_window="\n".join([f"line {i}" for i in range(n_lines)]))
    chunks = chunk_incident(inc)
    log_chunks = [c for c in chunks if c.chunk_type == "log"]

    all_content = "\n".join(c.content for c in log_chunks)
    for i in range(n_lines):
        assert f"line {i}" in all_content

    expected_blocks = -(-n_lines // _LOG_LINES_PER_CHUNK)
    assert len(log_chunks) == expected_blocks


def test_deploy_chunk_per_deploy() -> None:
    inc = _incident()
    chunks = chunk_incident(inc)
    deploy_chunks = [c for c in chunks if c.chunk_type == "deploy"]
    assert len(deploy_chunks) == len(inc.recent_deploys)


def test_deploy_chunk_content_includes_sha_and_message() -> None:
    inc = _incident()
    chunks = chunk_incident(inc)
    deploy_chunks = [c for c in chunks if c.chunk_type == "deploy"]
    for deploy, chunk in zip(inc.recent_deploys, deploy_chunks, strict=True):
        assert deploy.sha in chunk.content
        assert deploy.message in chunk.content
        assert deploy.author in chunk.content


def test_chunk_ids_are_unique() -> None:
    inc = _incident()
    chunks = chunk_incident(inc)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunk_incident_id_propagated() -> None:
    inc = _incident()
    for chunk in chunk_incident(inc):
        assert chunk.incident_id == inc.id


def test_chunk_subset_propagated() -> None:
    inc = _incident(id="adv-001", subset="adversarial", red_herring="A misleading signal")
    for chunk in chunk_incident(inc):
        assert chunk.subset == "adversarial"


def test_short_log_window_produces_single_log_chunk() -> None:
    # log_window must be ≥100 chars per schema; pad with a long header line.
    short_log = (
        "2024-01-15T03:41:00Z INFO checkout-service startup complete version=1.0.0\n"
        + "\n".join([f"line {i}" for i in range(4)])
    )
    inc = _incident(log_window=short_log)
    log_chunks = [c for c in chunk_incident(inc) if c.chunk_type == "log"]
    assert len(log_chunks) == 1


def test_deploy_chunk_metadata_has_sha() -> None:
    inc = _incident()
    chunks = chunk_incident(inc)
    for deploy, chunk in zip(
        inc.recent_deploys,
        [c for c in chunks if c.chunk_type == "deploy"],
        strict=True,
    ):
        assert chunk.metadata["sha"] == deploy.sha


def test_alert_chunk_metadata_has_severity() -> None:
    inc = _incident()
    alert_chunk = next(c for c in chunk_incident(inc) if c.chunk_type == "alert")
    assert alert_chunk.metadata["severity"] == "high"
    assert alert_chunk.metadata["affected_service"] == "checkout-service"


@pytest.mark.parametrize("n_deploys", [5, 7, 10])
def test_deploy_chunk_count_matches_deploy_list(n_deploys: int) -> None:
    inc = _incident(recent_deploys=_unique_deploys(n_deploys))
    deploy_chunks = [c for c in chunk_incident(inc) if c.chunk_type == "deploy"]
    assert len(deploy_chunks) == n_deploys
