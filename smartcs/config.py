"""Application configuration for SmartCS."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def parse_socketio_cors_origins(raw: str | None):
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value == "*":
        return "*"
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DEBUG = _bool_env("FLASK_DEBUG")
    TESTING = False

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///site.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "pool_pre_ping": True,
    }

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("HTTPS")
    WTF_CSRF_CHECK_DEFAULT = False

    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "eventlet").strip()
    SOCKETIO_MESSAGE_QUEUE = os.environ.get("SOCKETIO_MESSAGE_QUEUE")
    SOCKETIO_CORS_ALLOWED_ORIGINS = parse_socketio_cors_origins(
        os.environ.get(
            "SOCKETIO_CORS_ALLOWED_ORIGINS",
            os.environ.get("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5000,http://localhost:5000"),
        )
    )

    LOAD_EMOTION_MODEL_ON_STARTUP = _bool_env("LOAD_EMOTION_MODEL_ON_STARTUP", True)
    ENABLE_DEMO_SEED = _bool_env("ENABLE_DEMO_SEED", True)


class DevelopmentConfig(BaseConfig):
    DEBUG = BaseConfig.DEBUG
    SECRET_KEY = BaseConfig.SECRET_KEY or "dev-insecure-default-do-not-use-in-prod"


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_CHECK_DEFAULT = False
    LOAD_EMOTION_MODEL_ON_STARTUP = False
    ENABLE_DEMO_SEED = False
    SOCKETIO_ASYNC_MODE = "threading"
    RATELIMIT_ENABLED = False


class ProductionConfig(BaseConfig):
    @classmethod
    def validate(cls) -> None:
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set in production.")


CONFIGS = {
    "development": DevelopmentConfig,
    "dev": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
    "production": ProductionConfig,
    "prod": ProductionConfig,
}


def get_config(config_name: str | None = None):
    name = (config_name or os.environ.get("SMARTCS_ENV") or os.environ.get("FLASK_ENV") or "development").lower()
    config = CONFIGS.get(name, DevelopmentConfig)
    validate = getattr(config, "validate", None)
    if validate:
        validate()
    return config
