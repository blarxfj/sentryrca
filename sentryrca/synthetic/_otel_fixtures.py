"""Fetch and cache real commit metadata from the OTel demo repository.

Used to inject authentic commit SHAs and messages into synthetic deploy entries.
"""

import json
import random
from pathlib import Path
from typing import TypedDict

import httpx
import structlog

log = structlog.get_logger()

_OTEL_REPO = "open-telemetry/opentelemetry-demo"
_GITHUB_API = "https://api.github.com"
_DEFAULT_CACHE = Path("data/otel_commits.json")


class _GHAuthor(TypedDict):
    name: str
    date: str


class _GHCommitInner(TypedDict):
    message: str
    author: _GHAuthor


class _GHCommitItem(TypedDict):
    sha: str
    commit: _GHCommitInner


# Public type returned by load_otel_commits and sample_commits
OtelCommit = dict[str, str]


async def _fetch_from_github(limit: int) -> list[OtelCommit]:
    url = f"{_GITHUB_API}/repos/{_OTEL_REPO}/commits"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"per_page": limit}, headers=headers)
        resp.raise_for_status()

    raw: list[_GHCommitItem] = resp.json()
    commits: list[OtelCommit] = []
    for item in raw:
        inner = item["commit"]
        commits.append(
            {
                "sha": item["sha"][:12],
                "timestamp": inner["author"]["date"],
                "author": inner["author"]["name"],
                "message": inner["message"].split("\n")[0][:80],
            }
        )
    return commits


async def load_otel_commits(
    cache_path: Path = _DEFAULT_CACHE,
    *,
    limit: int = 60,
) -> list[OtelCommit]:
    """Return OTel demo repo commits, loading from cache_path if present."""
    if cache_path.exists():
        data: list[OtelCommit] = json.loads(cache_path.read_text())
        log.info("otel_commits_cache_hit", path=str(cache_path), count=len(data))
        return data

    log.info("fetching_otel_commits", repo=_OTEL_REPO, limit=limit)
    commits = await _fetch_from_github(limit)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(commits, indent=2))
    log.info("otel_commits_cached", path=str(cache_path), count=len(commits))
    return commits


def sample_commits(
    commits: list[OtelCommit],
    n: int = 7,
    *,
    rng: random.Random | None = None,
) -> list[OtelCommit]:
    """Return n commits sampled from the full list, sorted oldest-first."""
    _rng = rng or random.Random()
    sampled = _rng.sample(commits, min(n, len(commits)))
    return sorted(sampled, key=lambda c: c["timestamp"])
