from spinewatch.config import Settings


def test_defaults_with_empty_environment():
    settings = Settings.from_env({})

    assert settings.db_path == "books.db"
    assert settings.request_delay_min == 2.0
    assert settings.request_delay_max == 5.0
    assert settings.http_timeout == 20.0
    assert settings.browser_timeout == 30.0
    assert settings.max_escalations == 25
    assert settings.fixture_dir == "tests/fixtures"
    assert settings.log_level == "INFO"
    assert settings.cors_origins == ()


def test_every_field_overridable_from_environment():
    env = {
        "SPINEWATCH_DB_PATH": "/data/books.db",
        "SPINEWATCH_REQUEST_DELAY_MIN": "1.5",
        "SPINEWATCH_REQUEST_DELAY_MAX": "3.5",
        "SPINEWATCH_HTTP_TIMEOUT": "15",
        "SPINEWATCH_BROWSER_TIMEOUT": "45",
        "SPINEWATCH_MAX_ESCALATIONS": "10",
        "SPINEWATCH_FIXTURE_DIR": "/tmp/fixtures",
        "SPINEWATCH_LOG_LEVEL": "DEBUG",
        "SPINEWATCH_CORS_ORIGINS": "https://example.vercel.app",
    }

    settings = Settings.from_env(env)

    assert settings.db_path == "/data/books.db"
    assert settings.request_delay_min == 1.5
    assert settings.request_delay_max == 3.5
    assert settings.http_timeout == 15.0
    assert settings.browser_timeout == 45.0
    assert settings.max_escalations == 10
    assert settings.fixture_dir == "/tmp/fixtures"
    assert settings.log_level == "DEBUG"
    assert settings.cors_origins == ("https://example.vercel.app",)


def test_blank_environment_value_falls_back_to_default():
    settings = Settings.from_env({"SPINEWATCH_DB_PATH": ""})

    assert settings.db_path == "books.db"


def test_cors_origins_defaults_to_empty_tuple():
    settings = Settings.from_env({})

    assert settings.cors_origins == ()


def test_cors_origins_parsed_from_comma_separated_env():
    settings = Settings.from_env(
        {"SPINEWATCH_CORS_ORIGINS": "https://a.vercel.app, https://b.example.com"}
    )

    assert settings.cors_origins == ("https://a.vercel.app", "https://b.example.com")


def test_cors_origins_blank_value_falls_back_to_default():
    settings = Settings.from_env({"SPINEWATCH_CORS_ORIGINS": ""})

    assert settings.cors_origins == ()
