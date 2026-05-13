"""
Invest Solo -- Watchlist JSON File Store
Persists watchlist items to data/watchlist.json.
"""

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from backend.app.config import PROJECT_ROOT

WATCHLIST_PATH = PROJECT_ROOT / "data" / "watchlist.json"

_EMPTY_WATCHLIST = {
    "version": 1,
    "last_modified": "",
    "items": [],
}


class WatchlistStore:
    """Thread-safe JSON file store for watchlist items."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or WATCHLIST_PATH
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the watchlist file and parent dirs if they don't exist."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write(_EMPTY_WATCHLIST.copy())

    def _read(self) -> dict[str, Any]:
        try:
            with open(self._path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Error reading watchlist file: {exc}")
            return _EMPTY_WATCHLIST.copy()

    def _write(self, data: dict[str, Any]) -> None:
        data["last_modified"] = datetime.now(UTC).isoformat()
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error(f"Error writing watchlist file: {exc}")

    # -- public API --

    def get_items(self) -> list[dict[str, Any]]:
        """Return all watchlist items."""
        with self._lock:
            data = self._read()
            return data.get("items", [])

    def add_item(self, ticker: str, notes: str | None = None) -> dict[str, Any]:
        """Add a ticker to the watchlist. Returns the created item."""
        item = {
            "id": str(uuid.uuid4()),
            "ticker": ticker.upper(),
            "added_date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "notes": notes or "",
        }
        with self._lock:
            data = self._read()
            # Prevent duplicates
            existing = {i["ticker"] for i in data["items"]}
            if item["ticker"] in existing:
                logger.info(f"{ticker} already on watchlist")
                for i in data["items"]:
                    if i["ticker"] == item["ticker"]:
                        return i
            data["items"].append(item)
            self._write(data)
        logger.info(f"Added {ticker} to watchlist")
        return item

    def remove_item(self, item_id: str) -> bool:
        """Remove a watchlist item by id. Returns True if removed."""
        with self._lock:
            data = self._read()
            original_len = len(data["items"])
            data["items"] = [i for i in data["items"] if i["id"] != item_id]
            if len(data["items"]) < original_len:
                self._write(data)
                logger.info(f"Removed watchlist item {item_id}")
                return True
        logger.warning(f"Watchlist item {item_id} not found")
        return False
