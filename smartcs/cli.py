"""Flask CLI commands for local setup and open-source demos."""
from __future__ import annotations

from pathlib import Path

import click
from flask import Flask


@click.group("smartcs")
def smartcs_group() -> None:
    """SmartCS maintenance commands."""


@smartcs_group.command("init-db")
def init_db_command() -> None:
    """Create database tables and indexes."""
    from smartcs.bootstrap import initialize_database

    initialize_database()
    click.echo("Database initialized.")


@smartcs_group.command("seed-demo")
def seed_demo_command() -> None:
    """Seed demo accounts and sample customer-service data."""
    from smartcs.bootstrap import initialize_database, seed_demo_data

    initialize_database()
    seed_demo_data()
    click.echo("Demo data seeded.")


@smartcs_group.command("check-models")
def check_models_command() -> None:
    """Report optional model configuration without loading heavy weights."""
    from smartcs import legacy_app

    model_path = Path(legacy_app.MODEL_PATH)
    startup_status = (
        "enabled"
        if legacy_app.app.config.get("LOAD_EMOTION_MODEL_ON_STARTUP", True)
        else "disabled"
    )

    click.echo(f"Emotion model startup loading: {startup_status}")
    click.echo(f"Emotion model path: {model_path}")

    required_files = [
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.txt",
    ]
    missing = [name for name in required_files if not (model_path / name).exists()]
    if missing:
        click.echo("Emotion model metadata: incomplete")
        click.echo("Missing files: " + ", ".join(missing))
    else:
        click.echo("Emotion model metadata: present")


def register_cli_commands(app: Flask) -> None:
    """Register SmartCS CLI commands on the Flask app."""
    app.cli.add_command(smartcs_group)