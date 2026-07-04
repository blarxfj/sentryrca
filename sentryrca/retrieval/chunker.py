"""Split an IncidentCase into retrievable chunks."""

from dataclasses import dataclass, field
from typing import Any

from sentryrca.schema.incident import IncidentCase

_LOG_LINES_PER_CHUNK = 30


@dataclass
class ChunkRecord:
    id: str
    incident_id: str
    subset: str
    chunk_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_incident(incident: IncidentCase) -> list[ChunkRecord]:
    """Return all chunks for a single incident.

    Chunk types:
    - alert:  the full alert_text as a single chunk
    - log:    log_window split into blocks of LOG_LINES_PER_CHUNK lines
    - deploy: one chunk per deploy entry, formatted as prose
    """
    chunks: list[ChunkRecord] = []

    chunks.append(
        ChunkRecord(
            id=f"{incident.id}_alert_0",
            incident_id=incident.id,
            subset=incident.subset,
            chunk_type="alert",
            content=incident.alert_text,
            metadata={
                "affected_service": incident.affected_service,
                "severity": incident.severity,
                "category": incident.category,
            },
        )
    )

    log_lines = incident.log_window.splitlines()
    for i in range(0, len(log_lines), _LOG_LINES_PER_CHUNK):
        block = "\n".join(log_lines[i : i + _LOG_LINES_PER_CHUNK])
        if block.strip():
            chunks.append(
                ChunkRecord(
                    id=f"{incident.id}_log_{i // _LOG_LINES_PER_CHUNK}",
                    incident_id=incident.id,
                    subset=incident.subset,
                    chunk_type="log",
                    content=block,
                    metadata={
                        "affected_service": incident.affected_service,
                        "log_block_index": i // _LOG_LINES_PER_CHUNK,
                    },
                )
            )

    for deploy in incident.recent_deploys:
        files = ", ".join(deploy.changed_files) if deploy.changed_files else "no files recorded"
        content = (
            f"Deploy {deploy.sha} by {deploy.author} at {deploy.timestamp}.\n"
            f"Message: {deploy.message}\n"
            f"Changed files: {files}"
        )
        chunks.append(
            ChunkRecord(
                id=f"{incident.id}_deploy_{deploy.sha[:12]}",
                incident_id=incident.id,
                subset=incident.subset,
                chunk_type="deploy",
                content=content,
                metadata={
                    "sha": deploy.sha,
                    "author": deploy.author,
                    "timestamp": deploy.timestamp,
                },
            )
        )

    return chunks
