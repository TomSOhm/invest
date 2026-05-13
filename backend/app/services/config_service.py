"""
Invest Solo -- Configuration Service
Thin wrapper that exposes settings.yaml as a typed singleton.
"""

from backend.app.config import AppConfig, settings


def get_settings() -> AppConfig:
    """Return the global AppConfig singleton."""
    return settings
