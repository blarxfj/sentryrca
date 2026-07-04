CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Retrieval corpus ─────────────────────────────────────────────────────────
-- Each incident is split into chunks (alert, log segments, deploy entries).
-- Dense search uses HNSW on the embedding column; FTS uses GIN on the generated
-- tsvector. Both paths are fused via RRF in the application layer.

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    subset      TEXT NOT NULL,      -- synthetic | real_derived | adversarial
    chunk_type  TEXT NOT NULL,      -- alert | log | deploy | runbook
    content     TEXT NOT NULL,
    embedding   vector(384),        -- bge-small-en-v1.5
    fts_vector  tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    metadata    JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_fts_gin_idx
    ON chunks USING gin (fts_vector);

CREATE INDEX IF NOT EXISTS chunks_incident_id_idx
    ON chunks (incident_id);

-- ─── RCA audit store ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS rca_runs (
    id              TEXT PRIMARY KEY,
    incident_id     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version   TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    agent_step_count INT NOT NULL,
    total_tokens    INT NOT NULL,
    total_cost_usd  NUMERIC(10, 6) NOT NULL,
    p95_step_latency_ms INT NOT NULL,
    output          JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS rca_runs_incident_id_idx ON rca_runs (incident_id);
CREATE INDEX IF NOT EXISTS rca_runs_created_at_idx  ON rca_runs (created_at DESC);
