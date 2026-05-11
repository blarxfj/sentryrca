from pydantic import BaseModel, Field

from sentryrca.schema.incident import IncidentCase


class EvalCase(BaseModel):
    """An IncidentCase plus ground-truth labels used by the eval harness."""

    incident: IncidentCase
    expected_top_hypothesis: str = Field(
        ...,
        description="The root-cause hypothesis the RCA agent should rank #1",
    )
    expected_affected_service: str = Field(
        ...,
        description=(
            "Service the RCA agent should identify as primary — "
            "may differ from incident.affected_service in adversarial cases "
            "where the red herring points at a different service"
        ),
    )
    human_validated: bool = Field(
        default=False,
        description="True when a human reviewer has signed off on this case",
    )
    human_notes: str | None = Field(
        default=None,
        description="Reviewer caveats, edge-case flags, or disagreements with the LLM judge",
    )
