"""
Invest Solo -- Backend Configuration
Loads settings.yaml and ensures src modules are importable.
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Resolve project root (two levels up from this file: backend/app/config.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Ensure the project root is on sys.path so that `from src.xxx import ...` works
# when running `python -m uvicorn backend.app.main:app` from the project root.
_root_str = str(PROJECT_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

# ---------------------------------------------------------------------------
# settings.yaml loader
# ---------------------------------------------------------------------------
SETTINGS_PATH = PROJECT_ROOT / "settings.yaml"


def _load_settings() -> Dict[str, Any]:
    """Load settings.yaml from the project root."""
    if not SETTINGS_PATH.exists():
        raise FileNotFoundError(f"settings.yaml not found at {SETTINGS_PATH}")
    with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_RAW_SETTINGS: Dict[str, Any] = _load_settings()


# ---------------------------------------------------------------------------
# Typed AppConfig singleton
# ---------------------------------------------------------------------------
class AppConfig:
    """Typed accessor for all application settings."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self._raw = raw

    # -- project --
    @property
    def project_name(self) -> str:
        return self._raw["project"]["name"]

    @property
    def project_version(self) -> str:
        return self._raw["project"]["version"]

    # -- data --
    @property
    def primary_source(self) -> str:
        return self._raw["data"]["primary_source"]

    @property
    def cache_ttl_hours(self) -> int:
        return int(self._raw["data"]["cache_ttl_hours"])

    @property
    def max_retries(self) -> int:
        return int(self._raw["data"]["max_retries"])

    @property
    def request_delay_seconds(self) -> float:
        return float(self._raw["data"]["request_delay_seconds"])

    # -- pea --
    @property
    def pea_enabled(self) -> bool:
        return bool(self._raw["pea"]["enabled"])

    @property
    def pea_eligible_countries(self) -> List[str]:
        return [str(c).upper() for c in self._raw["pea"]["eligible_countries"]]

    @property
    def pea_max_deposit(self) -> float:
        return float(self._raw["pea"]["max_deposit"])

    @property
    def pea_pme_max_deposit(self) -> float:
        return float(self._raw["pea"]["pea_pme_max_deposit"])

    @property
    def pea_tax_rate_after_5y(self) -> float:
        return float(self._raw["pea"]["tax_rate_after_5y"])

    # -- valuation --
    @property
    def dcf_projection_years(self) -> int:
        return int(self._raw["valuation"]["dcf"]["projection_years"])

    @property
    def dcf_terminal_growth_rate(self) -> float:
        return float(self._raw["valuation"]["dcf"]["terminal_growth_rate"])

    @property
    def dcf_risk_free_rate(self) -> float:
        return float(self._raw["valuation"]["dcf"]["risk_free_rate"])

    @property
    def dcf_equity_risk_premium(self) -> float:
        return float(self._raw["valuation"]["dcf"]["equity_risk_premium"])

    # -- scoring --
    @property
    def scoring_weights(self) -> Dict[str, float]:
        s = self._raw["scoring"]
        return {
            "valuation": s["valuation_weight"],
            "financial_health": s["financial_health_weight"],
            "profitability": s["profitability_weight"],
            "growth": s["growth_weight"],
            "shareholder_return": s["shareholder_return_weight"],
            "risk": s["risk_weight"],
        }

    # -- signals --
    @property
    def signal_thresholds(self) -> Dict[str, Any]:
        return self._raw["signals"]

    # -- portfolio --
    @property
    def portfolio_max_single_position(self) -> float:
        return float(self._raw["portfolio"]["max_single_position"])

    @property
    def portfolio_max_sector_exposure(self) -> float:
        return float(self._raw["portfolio"]["max_sector_exposure"])

    # -- screener --
    @property
    def screener_min_market_cap(self) -> float:
        return float(self._raw["screener"]["min_market_cap"])

    @property
    def screener_exclude_sectors(self) -> List[str]:
        return self._raw["screener"].get("exclude_sectors", [])

    # -- logging --
    @property
    def log_level(self) -> str:
        return self._raw["logging"]["level"]

    @property
    def log_file(self) -> str:
        return self._raw["logging"]["file"]

    # -- raw access --
    @property
    def raw(self) -> Dict[str, Any]:
        return self._raw


settings = AppConfig(_RAW_SETTINGS)
