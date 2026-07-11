"""SmartCS application package."""
from __future__ import annotations

from smartcs.config import get_config


def create_app(config_name: str | None = None):
    """Return the configured Flask application."""
    from smartcs import legacy_app

    if config_name:
        legacy_app.app.config.from_object(get_config(config_name))
    return legacy_app.app


def create_socketio():
    from smartcs.extensions import socketio

    return socketio
