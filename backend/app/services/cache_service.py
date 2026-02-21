"""
Invest Solo -- Simple File-Based Cache Service
Stores JSON payloads in data/cache/ with TTL support.
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from backend.app.config import PROJECT_ROOT


class CacheService:
    """File-based JSON cache with TTL expiration."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self._cache_dir = cache_dir or (PROJECT_ROOT / "data" / "cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a safe file path."""
        safe_key = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a cached payload. Returns None if expired or missing."""
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                envelope = json.load(fh)
            expires_at = envelope.get("expires_at", 0)
            if time.time() > expires_at:
                logger.debug(f"Cache expired for key={key}")
                path.unlink(missing_ok=True)
                return None
            return envelope.get("payload")
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning(f"Cache read error for key={key}: {exc}")
            return None

    def set(self, key: str, payload: Dict[str, Any], ttl_seconds: int = 14400) -> None:
        """Store a payload with TTL (default 4 hours = 14400 seconds)."""
        path = self._key_to_path(key)
        envelope = {
            "key": key,
            "created_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
            "payload": payload,
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(envelope, fh, ensure_ascii=False, default=str)
            logger.debug(f"Cache set for key={key}, ttl={ttl_seconds}s")
        except OSError as exc:
            logger.warning(f"Cache write error for key={key}: {exc}")

    def invalidate(self, key: str) -> None:
        """Remove a single cache entry."""
        path = self._key_to_path(key)
        path.unlink(missing_ok=True)

    def clear_all(self) -> int:
        """Remove all cache files. Returns count of files removed."""
        count = 0
        for path in self._cache_dir.glob("*.json"):
            path.unlink(missing_ok=True)
            count += 1
        logger.info(f"Cache cleared: {count} entries removed")
        return count
