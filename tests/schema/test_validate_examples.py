"""Smoke test for the schema validate_examples runner."""

from sentryrca.schema.validate_examples import _build_valid_example, main


def test_build_valid_example_returns_rca_output() -> None:
    from sentryrca.schema.rca import RCAOutput

    rca = _build_valid_example()
    assert isinstance(rca, RCAOutput)
    assert rca.incident_id
    assert rca.evidence
    assert rca.timeline


def test_main_exits_cleanly() -> None:
    """main() must complete without raising."""
    main()
