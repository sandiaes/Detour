import pytest
from pydantic import ValidationError

from detour_api.settings import DEV_TOKEN_SECRET, Settings, get_settings, normalize_database_url


def make(**kwargs: object) -> Settings:
    return Settings.model_validate(kwargs)


def test_defaults_are_safe_for_local_use() -> None:
    s = make()
    assert s.environment == "local"
    assert s.database_url is None
    assert s.sqlalchemy_url is None
    assert s.token_secret is not None
    assert s.token_secret.get_secret_value() == DEV_TOKEN_SECRET
    assert s.map_style_url == "https://tiles.openfreemap.org/styles/liberty"
    assert [a.text for a in s.map_attribution] == [
        "OpenFreeMap",
        "© OpenMapTiles",
        "Data from OpenStreetMap",
    ]


def test_values_come_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DETOUR_ENVIRONMENT", "test")
    monkeypatch.setenv("DETOUR_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("DETOUR_MAP_STYLE_URL", "https://tiles.example.org/style.json")
    monkeypatch.setenv("DETOUR_DATABASE_URL", "postgresql://u:p@db.example.org:5432/postgres")
    monkeypatch.setenv(
        "DETOUR_MAP_ATTRIBUTION", '[{"text": "Example", "url": "https://example.org"}]'
    )
    s = Settings()
    assert s.environment == "test"
    assert s.log_level == "WARNING"
    assert s.map_style_url == "https://tiles.example.org/style.json"
    assert s.map_attribution[0].text == "Example"
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@db.example.org:5432/postgres"


def test_blank_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", "")
    monkeypatch.setenv("DETOUR_TOKEN_SECRET", "")
    s = Settings()
    assert s.database_url is None
    assert s.token_secret is not None
    assert s.token_secret.get_secret_value() == DEV_TOKEN_SECRET


def test_production_requires_its_own_token_secret() -> None:
    with pytest.raises(ValidationError, match="DETOUR_TOKEN_SECRET is required"):
        make(environment="production")
    assert make(environment="production", token_secret="x" * 32).environment == "production"


def test_short_token_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        make(token_secret="short")


def test_style_and_attribution_must_be_https_and_present() -> None:
    with pytest.raises(ValidationError, match="https"):
        make(map_style_url="http://insecure.example.org/style")
    with pytest.raises(ValidationError, match="https"):
        make(map_attribution=[{"text": "x", "url": "http://x.example.org"}])
    with pytest.raises(ValidationError, match="at least one"):
        make(map_attribution=[])


def test_unknown_environment_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(environment="staging")


def test_render_commit_variable_is_used_as_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc1234")
    assert Settings().release == "abc1234"


def test_secrets_are_not_shown_in_repr() -> None:
    s = make(
        database_url="postgresql://user:hunter2@db.example.org/postgres", token_secret="y" * 40
    )
    assert "hunter2" not in repr(s)
    assert "y" * 40 not in repr(s)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ],
)
def test_database_url_normalisation(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DETOUR_ENVIRONMENT", "test")
    first = get_settings()
    assert get_settings() is first
    get_settings.cache_clear()
