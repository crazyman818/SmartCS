"""Shared application bootstrap helpers."""
from __future__ import annotations

from flask import Flask


def initialize_database() -> None:
    """Create database tables, indexes, and SQLite connection hooks."""
    from smartcs import legacy_app

    legacy_app.db.create_all()
    legacy_app._ensure_indexes()
    legacy_app._register_sqlite_pragma()


def seed_demo_data() -> None:
    """Seed configured demo accounts and sample data."""
    from smartcs import legacy_app

    legacy_app.seed_defaults()


def bootstrap_application(
    app: Flask,
    *,
    seed_demo: bool = True,
    load_model: bool | None = None,
) -> None:
    """Run startup tasks shared by local and container entrypoints."""
    from smartcs import legacy_app

    with app.app_context():
        legacy_app.db.create_all()
        legacy_app._ensure_indexes()
        if seed_demo:
            legacy_app.seed_defaults()

        should_load_model = (
            app.config.get("LOAD_EMOTION_MODEL_ON_STARTUP", True)
            if load_model is None
            else load_model
        )
        if should_load_model:
            legacy_app.load_emotion_model()

        legacy_app._register_sqlite_pragma()