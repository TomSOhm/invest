"""
Invest Solo -- Configuration Service
Thin wrapper that exposes settings.yaml as a typed singleton.
"""
from backend.app.config import settings, AppConfig


def get_settings() -> AppConfig:
    """Return the global AppConfig singleton."""
    return settings
