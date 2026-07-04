"""LLM-as-judge for top-1 RCA accuracy.

Scores whether the agent's top_hypothesis and likely_root_cause align with the
ground-truth root cause. Uses claude-haiku for cost efficiency.
"""

import json
import re
from typing import Any

import litellm
import structlog

from sentryrca.config import settings
from sentryrca.observability import traced
from sentryrca.schema.rca import RCAOutput

log = structlog.get_logger()

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

_JUDGE_PROMPT = """\
You are an expert SRE evaluating an AI-generated root cause analysis.

## Ground-truth root cause
{ground_truth}

## Agent's top hypothesis
{top_hypothesis}

## Agent's likely root cause
{likely_root_cause}

## Task
Score whether the agent correctly identified the root cause.

Return a JSON object with:
- "score": integer 0, 1, or 2
  - 2 = correct: agent identified the same root cause (same failure mode, same component)
  - 1 = partial: agent identified the right component but wrong mechanism, or vice versa
  - 0 = wrong: agent identified a different root cause entirely
- "reasoning": one sentence explaining the score

Return only the JSON object, no markdown fences.
"""


@traced(name="eval.judge")
async def judge_top1(
    rca: RCAOutput,
    ground_truth_root_cause: str,
) -> tuple[int, str]:
    """Return (score 0-2, reasoning string)."""
    prompt = _JUDGE_PROMPT.format(
        ground_truth=ground_truth_root_cause,
        top_hypothesis=rca.top_hypothesis,
        likely_root_cause=rca.likely_root_cause,
    )
    response = await litellm.acompletion(
        model=settings.litellm_model_fast,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    raw = (response.choices[0].message.content or "").strip()
    m = _FENCE_RE.match(raw)
    content = m.group(1).strip() if m else raw
    try:
        result: dict[str, Any] = json.loads(content) if content else {}
        raw_score = result.get("score", 0)
        score = int(raw_score) if isinstance(raw_score, (int, float)) else 0
        reasoning = str(result.get("reasoning", ""))
        return score, reasoning
    except (json.JSONDecodeError, ValueError):
        log.warning("judge: failed to parse response", content=content[:200])
        return 0, "parse error"
