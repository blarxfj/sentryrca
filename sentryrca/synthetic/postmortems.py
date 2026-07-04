"""Parse real post-mortems from danluu/post-mortems into IncidentCase format.

Run: python -m sentryrca.synthetic.postmortems
Output: data/incidents/real_derived/real-001.json … real-010.json

Strategy:
  1. Fetch the README.md from danluu/post-mortems via the GitHub raw content API.
  2. Extract (company, description) pairs from the markdown bullet links.
  3. For each of the first 10, call Claude to synthesize a plausible IncidentCase
     with subset="real_derived" — inspired by the described incident but with
     generated technical details (logs, stack traces, deploy entries).
"""

import asyncio
import re
import sys
from pathlib import Path

import httpx
import structlog
from pydantic import ValidationError

from sentryrca.schema.incident import IncidentCase
from sentryrca.synthetic._llm import call_llm_json
from sentryrca.synthetic._prompts import POSTMORTEM_SYSTEM_PROMPT, postmortem_user_prompt

log = structlog.get_logger()

OUTPUT_DIR = Path("data/incidents/real_derived")
CONCURRENCY = 3
TARGET_COUNT = 10

_README_URL = "https://raw.githubusercontent.com/danluu/post-mortems/master/README.md"
_BULLET_RE = re.compile(
    r"^\[([^\]]+)\]\([^)]+\)\.\s*(.+)$",
    re.MULTILINE,
)


async def _fetch_readme() -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(_README_URL)
        resp.raise_for_status()
        return resp.text


def _extract_postmortems(readme: str, max_count: int = 20) -> list[tuple[str, str]]:
    """Return (company, description) pairs from markdown bullet links."""
    matches = _BULLET_RE.findall(readme)
    results = [
        (company.strip(), desc.strip()) for company, desc in matches if len(desc.strip()) >= 30
    ]
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for company, desc in results:
        if company not in seen:
            seen.add(company)
            unique.append((company, desc))
        if len(unique) >= max_count:
            break
    return unique


async def _generate_one(
    incident_id: str,
    company: str,
    description: str,
    semaphore: asyncio.Semaphore,
) -> IncidentCase:
    async with semaphore:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": POSTMORTEM_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": postmortem_user_prompt(
                    company=company,
                    description=description,
                    incident_id=incident_id,
                ),
            },
        ]

        for attempt in range(3):
            raw = await call_llm_json(messages)
            try:
                return IncidentCase.model_validate_json(raw)
            except ValidationError as exc:
                log.warning(
                    "postmortem_validation_failed",
                    incident_id=incident_id,
                    attempt=attempt + 1,
                    errors=str(exc.errors())[:300],
                )
                if attempt == 2:
                    raise
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Validation errors:\n{exc.errors()}\n\n"
                            "Fix every error and return valid JSON only."
                        ),
                    }
                )

        raise RuntimeError(f"unreachable: {incident_id}")


async def generate_all(output_dir: Path = OUTPUT_DIR) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("fetching_postmortem_list")
    readme = await _fetch_readme()
    postmortems = _extract_postmortems(readme, max_count=TARGET_COUNT * 2)
    log.info("extracted_postmortems", count=len(postmortems))

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks: list[tuple[Path, asyncio.Task[IncidentCase]]] = []

    for i, (company, description) in enumerate(postmortems[:TARGET_COUNT], start=1):
        incident_id = f"real-{i:03d}"
        out_path = output_dir / f"{incident_id}.json"
        if out_path.exists():
            log.info("skipping_existing", incident_id=incident_id)
            continue
        task: asyncio.Task[IncidentCase] = asyncio.create_task(
            _generate_one(
                incident_id=incident_id,
                company=company,
                description=description,
                semaphore=semaphore,
            )
        )
        tasks.append((out_path, task))

    skipped = TARGET_COUNT - len(tasks)
    if not tasks:
        log.info("all_postmortems_already_generated")
        return {"ok": 0, "skipped": skipped, "failed": 0}

    log.info("generating_postmortems", count=len(tasks))
    results = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)

    ok = failed = 0
    for (out_path, _), result in zip(tasks, results, strict=True):
        if isinstance(result, BaseException):
            log.error("postmortem_failed", path=str(out_path), error=str(result))
            failed += 1
        else:
            out_path.write_text(result.model_dump_json(indent=2))
            log.info("generated", path=str(out_path))
            ok += 1

    log.info("postmortems_complete", ok=ok, skipped=skipped, failed=failed)
    return {"ok": ok, "skipped": skipped, "failed": failed}


async def main() -> None:
    counts = await generate_all()
    if counts["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
