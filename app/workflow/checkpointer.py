import logging
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import settings

logger = logging.getLogger("filingguard.workflow.checkpointer")

_lock = threading.Lock()
# Cache mapping normalized path -> (sqlite3.Connection, SqliteSaver)
_active_savers: Dict[str, Tuple[sqlite3.Connection, SqliteSaver]] = {}


def get_checkpoint_db_path() -> Path:
    """Return SQLite database path for workflow state checkpoints."""
    db_path = settings.DATABASE_DIR / "checkpoints.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_checkpointer(db_path: Optional[Path] = None) -> SqliteSaver:
    """Instantiate or retrieve a managed SQLite checkpointer for LangGraph workflows.

    Features:
    - Thread-safe singleton saver per database path to prevent connection leaks.
    - Configures 30.0s connection timeout and busy_timeout=30000 to prevent locked errors.
    - Enables WAL journal mode for safe concurrent reads and durable serialized writes.
    - Configures synchronous=NORMAL for durability and high throughput without lock contention.
    - Idempotently runs saver.setup() once per connection.
    """
    target_path = str((db_path or get_checkpoint_db_path()).resolve())

    with _lock:
        if target_path in _active_savers:
            conn, saver = _active_savers[target_path]
            # Verify that connection is still alive and responsive
            try:
                conn.execute("SELECT 1;")
                return saver
            except Exception as e:
                logger.warning(f"Existing checkpointer connection was closed or invalid: {e}. Reconnecting...")
                try:
                    conn.close()
                except Exception:
                    pass
                _active_savers.pop(target_path, None)

        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")

        saver = SqliteSaver(conn)
        saver.setup()
        _active_savers[target_path] = (conn, saver)
        logger.debug(f"Initialized managed SQLite checkpointer for {target_path} (WAL mode, timeout=30s)")
        return saver


def close_checkpointer(db_path: Optional[Path] = None) -> None:
    """Safely close and deregister the checkpointer connection for target_path."""
    target_path = str((db_path or get_checkpoint_db_path()).resolve())
    with _lock:
        entry = _active_savers.pop(target_path, None)
        if entry:
            conn, _ = entry
            try:
                conn.close()
                logger.debug(f"Closed SQLite checkpointer connection for {target_path}")
            except Exception as e:
                logger.warning(f"Error closing checkpointer connection: {e}")


def close_all_checkpointers() -> None:
    """Close all active checkpointer connections."""
    with _lock:
        for path_str, (conn, _) in list(_active_savers.items()):
            try:
                conn.close()
            except Exception:
                pass
        _active_savers.clear()

