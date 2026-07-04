"""Deterministic citation-faithfulness checks.

Every EvidenceItem.excerpt must appear verbatim in the incident corpus text.
This is a hard rule — not LLM-judged. See CLAUDE.md non-negotiables.
"""

from sentryrca.schema.incident import IncidentCase
from sentryrca.schema.rca import RCAOutput


def build_corpus_text(incident: IncidentCase) -> str:
    """Concatenate all searchable text from an incident into a single string.

    Deploy entries are formatted to match the chunker's exact output so that
    verbatim excerpt checks pass for deploy evidence items.
    """
    parts = [incident.alert_text, incident.log_window]
    for d in incident.recent_deploys:
        files = ", ".join(d.changed_files) if d.changed_files else "no files recorded"
        parts.append(
            f"Deploy {d.sha} by {d.author} at {d.timestamp}.\n"
            f"Message: {d.message}\n"
            f"Changed files: {files}"
        )
    return "\n".join(parts)


def verify_excerpt_in_corpus(excerpt: str, corpus_text: str) -> bool:
    """Return True if `excerpt` appears verbatim (substring) in `corpus_text`."""
    return excerpt.strip() in corpus_text


def check_citation_faithfulness(
    rca: RCAOutput,
    incident: IncidentCase,
) -> tuple[int, int]:
    """Return (passed, total) counts for evidence excerpt faithfulness.

    An excerpt passes if it appears verbatim in the incident corpus text.
    """
    corpus_text = build_corpus_text(incident)
    total = len(rca.evidence)
    passed = sum(1 for e in rca.evidence if verify_excerpt_in_corpus(e.excerpt, corpus_text))
    return passed, total
