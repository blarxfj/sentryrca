from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application database
    database_url: str = Field(
        default="postgresql+asyncpg://sentryrca:sentryrca@localhost:5433/sentryrca"
    )

    # Langfuse SDK
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    # LLM model routing (referenced by name, not hardcoded)
    litellm_model_reasoning: str = "claude-sonnet-4-6"
    litellm_model_fast: str = "claude-haiku-4-5-20251001"

    # Anthropic
    anthropic_api_key: str | None = None


settings = Settings()
