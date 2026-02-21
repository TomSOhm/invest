"""
Invest Solo -- Portfolio JSON File Store
Persists portfolio positions to data/portfolio.json.
"""
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.app.config import PROJECT_ROOT

PORTFOLIO_PATH = PROJECT_ROOT / "data" / "portfolio.json"

_EMPTY_PORTFOLIO = {
    "version": 1,
    "last_modified": "",
    "positions": [],
}


class PortfolioStore:
    """Thread-safe JSON file store for portfolio positions."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or PORTFOLIO_PATH
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the portfolio file and parent dirs if they don't exist."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write(_EMPTY_PORTFOLIO.copy())

    def _read(self) -> Dict[str, Any]:
        """Read the JSON file and return its contents."""
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Error reading portfolio file: {exc}")
            return _EMPTY_PORTFOLIO.copy()

    def _write(self, data: Dict[str, Any]) -> None:
        """Write data to the JSON file."""
        data["last_modified"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error(f"Error writing portfolio file: {exc}")

    # -- public API --

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return all stored positions."""
        with self._lock:
            data = self._read()
            return data.get("positions", [])

    def add_position(
        self,
        ticker: str,
        quantity: float,
        buy_price: float,
        buy_date: Optional[str] = None,
        account_type: str = "pea",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a new position and return it (including generated id)."""
        position = {
            "id": str(uuid.uuid4()),
            "ticker": ticker.upper(),
            "quantity": quantity,
            "buy_price": buy_price,
            "buy_date": buy_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "account_type": account_type,
            "notes": notes or "",
        }
        with self._lock:
            data = self._read()
            data["positions"].append(position)
            self._write(data)
        logger.info(f"Added position: {ticker} x{quantity} @ {buy_price}")
        return position

    def update_position(self, position_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update fields on an existing position.
        Returns the updated position or None if not found.
        """
        with self._lock:
            data = self._read()
            for pos in data["positions"]:
                if pos["id"] == position_id:
                    for key in ("quantity", "buy_price", "buy_date", "notes"):
                        if key in updates and updates[key] is not None:
                            pos[key] = updates[key]
                    self._write(data)
                    logger.info(f"Updated position {position_id}")
                    return pos
        logger.warning(f"Position {position_id} not found")
        return None

    def remove_position(self, position_id: str) -> bool:
        """Remove a position by id. Returns True if found and removed."""
        with self._lock:
            data = self._read()
            original_len = len(data["positions"])
            data["positions"] = [p for p in data["positions"] if p["id"] != position_id]
            if len(data["positions"]) < original_len:
                self._write(data)
                logger.info(f"Removed position {position_id}")
                return True
        logger.warning(f"Position {position_id} not found for removal")
        return False
