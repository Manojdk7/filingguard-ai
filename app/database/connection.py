import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator
from app.config import settings

logger = logging.getLogger("filingguard.database")


def get_db_path() -> str:
    """Return SQLite database path string and ensure directory exists."""
    db_path = settings.sqlite_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional SQLite database connection."""
    path = get_db_path()
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction rolled back: {e}")
        raise
    finally:
        conn.close()


def check_db_health() -> bool:
    """Verify that SQLite can execute a query."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 AS healthy;")
            result = cursor.fetchone()
            return result is not None and result["healthy"] == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

