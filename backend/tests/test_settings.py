"""Settings must load from defaults, be overridable by env, and stay local-only."""

import pytest

from app.core.settings import Settings, get_settings


def test_defaults_are_local_and_free() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "mock"
    assert settings.ollama_url.startswith("http://localhost")
    assert settings.sim_dt == pytest.approx(0.1)
    assert settings.sim_tick_rate == pytest.approx(10.0)


def test_environment_overrides_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_SEED", "999")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MAX_AGENTS", "3")

    settings = Settings(_env_file=None)

    assert settings.sim_seed == 999
    assert settings.llm_provider == "ollama"
    assert settings.llm_max_agents == 3


def test_database_url_lives_under_data_dir(tmp_path: object) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)

    assert settings.database_url.startswith("sqlite:///")
    assert settings.database_url.endswith("gametheory.db")


def test_invalid_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="sim_tick_rate"):
        Settings(_env_file=None, sim_tick_rate=0)


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
