"""Format an RCAOutput as Slack-flavoured markdown (Block Kit mrkdwn)."""

from sentryrca.schema.rca import RCAOutput

_SEVERITY_EMOJI = {
    "critical": ":red_circle:",
    "high": ":large_orange_circle:",
    "medium": ":large_yellow_circle:",
    "low": ":large_blue_circle:",
}


def format_slack(rca: RCAOutput, run_id: str | None = None) -> str:
    """Return a Slack mrkdwn string for an RCAOutput."""
    emoji = _SEVERITY_EMOJI.get(rca.severity, ":white_circle:")
    lines: list[str] = []

    lines.append(
        f"{emoji} *RCA — {rca.incident_id}* | {rca.severity.upper()} | `{rca.affected_service}`"
    )
    lines.append("")

    lines.append(f"*Root cause*\n> {rca.likely_root_cause}")
    lines.append("")

    lines.append(f"*Top hypothesis* (confidence: {rca.confidence:.0%})\n> {rca.top_hypothesis}")
    lines.append("")

    if rca.alternative_hypotheses:
        lines.append("*Alternative hypotheses*")
        for h in rca.alternative_hypotheses:
            lines.append(f"• {h}")
        lines.append("")

    lines.append("*Timeline*")
    for entry in rca.timeline:
        lines.append(f"• `{entry.timestamp}` — {entry.event}")
    lines.append("")

    lines.append("*Recommended actions*")
    for i, action in enumerate(rca.recommended_actions, 1):
        lines.append(f"{i}. {action}")
    lines.append("")

    if rca.rollback_candidate:
        lines.append(f"*Rollback candidate* `{rca.rollback_candidate}`")
        lines.append("")

    if rca.unknowns:
        lines.append("*Unknowns*")
        for u in rca.unknowns:
            lines.append(f"• {u}")
        lines.append("")

    lines.append(
        f"_Evidence: {len(rca.evidence)} items · "
        f"Tokens: {rca.total_tokens:,} · "
        f"Steps: {rca.agent_step_count} · "
        f"p95 latency: {rca.p95_step_latency_ms}ms · "
        f"Model: {rca.model_version}_"
    )

    if run_id:
        lines.append(f"_Run ID: `{run_id}`_")

    return "\n".join(lines)
