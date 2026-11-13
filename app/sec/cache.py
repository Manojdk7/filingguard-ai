import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional
from app.config import settings

logger = logging.getLogger("filingguard.sec.cache")


class SECCache:
    """Local filesystem cache for SEC JSON responses."""

    def __init__(self, cache_dir: Optional[Path] = None, ttl_hours: Optional[int] = None, enabled: Optional[bool] = None):
        self.cache_dir = cache_dir or (settings.DATA_DIR / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = (ttl_hours if ttl_hours is not None else settings.SEC_CACHE_TTL_HOURS) * 3600
        self.enabled = enabled if enabled is not None else settings.SEC_CACHE_ENABLED

    def _get_cache_path(self, key: str) -> Path:
        """Derive a safe filesystem path for a given cache key."""
        hashed_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{hashed_key}.json"

    def get(self, key: str) -> Optional[Any]:
        """Retrieve data from cache if present, unexpired, and valid."""
        if not self.enabled:
            return None

        cache_path = self._get_cache_path(key)
        if not cache_path.exists():
            return None

        try:
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime > self.ttl_seconds:
                logger.info(f"Cache expired for key: {key}")
                try:
                    cache_path.unlink()
                except OSError:
                    pass
                return None

            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.debug(f"Cache hit for key: {key}")
                return data
        except Exception as e:
            logger.warning(f"Cache read/parse failed for {cache_path}: {e}. Removing corrupt cache entry.")
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None

    def set(self, key: str, value: Any) -> None:
        """Save JSON serializable data to cache."""
        if not self.enabled:
            return

        cache_path = self._get_cache_path(key)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False)
            logger.debug(f"Cached data for key: {key}")
        except Exception as e:
            logger.error(f"Failed to write cache for key {key}: {e}")

    def clear(self) -> None:
        """Clear all entries in this cache directory."""
        for file in self.cache_dir.glob("*.json"):
            try:
                file.unlink()
            except OSError:
                pass

