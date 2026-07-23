from book_monitor.config import Settings


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


def test_every_field_overridable_from_environment():
    env = {
        "BOOKMON_DB_PATH": "/data/books.db",
        "BOOKMON_REQUEST_DELAY_MIN": "1.5",
        "BOOKMON_REQUEST_DELAY_MAX": "3.5",
        "BOOKMON_HTTP_TIMEOUT": "15",
        "BOOKMON_BROWSER_TIMEOUT": "45",
        "BOOKMON_MAX_ESCALATIONS": "10",
        "BOOKMON_FIXTURE_DIR": "/tmp/fixtures",
        "BOOKMON_LOG_LEVEL": "DEBUG",
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


def test_blank_environment_value_falls_back_to_default():
    settings = Settings.from_env({"BOOKMON_DB_PATH": ""})

    assert settings.db_path == "books.db"
