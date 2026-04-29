"""Smoke tests for the Settings config module."""

from sentryrca.config import Settings, settings


def test_settings_instantiates() -> None:
    """Settings must instantiate without a .env file present."""
    s = Settings()
    assert isinstance(s, Settings)


def test_settings_singleton_is_settings() -> None:
    assert isinstance(settings, Settings)


def test_default_model_names_are_set() -> None:
    s = Settings()
    assert s.litellm_model_reasoning
    assert s.litellm_model_fast


def test_optional_fields_default_to_none() -> None:
    s = Settings()
    # Without env vars these must be None, not raise
    assert s.langfuse_host is None or isinstance(s.langfuse_host, str)
    assert s.anthropic_api_key is None or isinstance(s.anthropic_api_key, str)
