import sqlite3
from app.config import settings
from app.database.connection import get_db_connection, check_db_health


def test_database_connection():
    assert check_db_health() is True

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TEMPORARY TABLE test_ping (id INTEGER PRIMARY KEY, msg TEXT);")
        cursor.execute("INSERT INTO test_ping (msg) VALUES ('pong');")
        cursor.execute("SELECT msg FROM test_ping WHERE id = 1;")
        row = cursor.fetchone()
        assert row["msg"] == "pong"


def test_settings_loaded():
    assert settings.APP_ENV in ["development", "test", "production"]
    assert settings.SEC_USER_AGENT != ""
    assert settings.SEC_REQUEST_TIMEOUT > 0
    assert settings.sqlite_db_path.name.endswith(".db")

