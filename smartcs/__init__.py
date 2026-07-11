"""SmartCS application package."""
from __future__ import annotations

from smartcs.config import get_config


def create_app(config_name: str | None = None):
    """Return the configured Flask application."""
    from smartcs import legacy_app
    from smartcs.cli import register_cli_commands
    from smartcs.routes.auth import register_auth_routes
    from smartcs.routes.chat import register_chat_routes
    from smartcs.routes.refunds import register_refund_routes
    from smartcs.routes.dashboard import register_dashboard_routes
    from smartcs.routes.knowledge import register_knowledge_routes

    if config_name:
        legacy_app.app.config.from_object(get_config(config_name))
    register_cli_commands(legacy_app.app)
    register_auth_routes(legacy_app.app)
    register_chat_routes(legacy_app.app)
    register_refund_routes(legacy_app.app)
    register_dashboard_routes(legacy_app.app)
    register_knowledge_routes(legacy_app.app)
    return legacy_app.app


def create_socketio():
    from smartcs.extensions import socketio

    return socketio
