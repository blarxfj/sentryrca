from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Category = Literal[
    "db_saturation",
    "deploy_regression",
    "dependency_outage",
    "config_error",
    "resource_exhaustion",
]

Severity = Literal["low", "medium", "high", "critical"]

Subset = Literal["synthetic", "real_derived", "adversarial"]


class DeployEntry(BaseModel):
    sha: str = Field(..., min_length=7, max_length=40, description="Git commit SHA")
    timestamp: str = Field(..., description="ISO 8601 deploy timestamp")
    author: str
    message: str = Field(..., description="First line of the commit message")
    changed_files: list[str] = Field(
        default_factory=list,
        description="Files touched by this commit",
    )

    @field_validator("timestamp")
    @classmethod
    def _timestamp_looks_like_iso8601(cls, v: str) -> str:
        if not v[:10].count("-") == 2:
            raise ValueError(f"timestamp must be ISO 8601, got {v!r}")
        return v


class IncidentCase(BaseModel):
    id: str = Field(
        ...,
        pattern=r"^(syn|real|adv)-\d{3}$",
        description="Stable incident identifier: syn-NNN, real-NNN, or adv-NNN",
    )
    subset: Subset
    category: Category
    affected_service: str = Field(
        ...,
        description="Primary OTel demo service impacted by the incident",
    )
    severity: Severity
    alert_text: str = Field(
        ...,
        min_length=20,
        description="The alert or page that triggered incident response",
    )
    log_window: str = Field(
        ...,
        min_length=100,
        description="50-200 lines of service logs surrounding the incident, newline-separated",
    )
    recent_deploys: list[DeployEntry] = Field(
        ...,
        min_length=5,
        max_length=10,
        description="5-10 deploy entries preceding the incident, oldest first",
    )
    ground_truth_root_cause: str = Field(
        ...,
        description="Specific and technical root cause — references deploy SHA where applicable",
    )
    ground_truth_remediation: str = Field(
        ...,
        description="Concrete remediation achievable within 2 hours",
    )
    red_herring: str | None = Field(
        default=None,
        description=(
            "Adversarial only: describes the suspicious signal that is NOT the root cause "
            "and cites exculpatory evidence present in the log_window"
        ),
    )

    @model_validator(mode="after")
    def _red_herring_invariant(self) -> "IncidentCase":
        if self.subset == "adversarial" and not self.red_herring:
            raise ValueError("adversarial incidents must provide a non-empty red_herring field")
        if self.subset != "adversarial" and self.red_herring is not None:
            raise ValueError(
                f"red_herring is only valid for adversarial incidents (got subset={self.subset!r})"
            )
        return self
