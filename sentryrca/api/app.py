"""FastAPI application — RCA endpoint + health check."""

from fastapi import FastAPI, HTTPException

from sentryrca.agents import run_rca
from sentryrca.schema.incident import IncidentCase
from sentryrca.schema.rca import RCAOutput

app = FastAPI(
    title="SentryRCA",
    description="Multi-agent root cause analysis for production incidents",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/rca", response_model=RCAOutput)
async def create_rca(incident: IncidentCase) -> RCAOutput:
    """Run the full multi-agent RCA pipeline for a single incident."""
    try:
        return await run_rca(incident)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
