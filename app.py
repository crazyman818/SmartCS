"""Backward-compatible local entrypoint for SmartCS."""
from smartcs import create_app
from smartcs.extensions import socketio
from smartcs.legacy_app import *  # noqa: F401,F403 - keep old imports working.


def main() -> None:
    from smartcs import legacy_app

    flask_app = create_app()
    with flask_app.app_context():
        legacy_app.db.create_all()
        legacy_app._ensure_indexes()
        legacy_app.seed_defaults()
        if flask_app.config.get("LOAD_EMOTION_MODEL_ON_STARTUP", True):
            legacy_app.load_emotion_model()
        legacy_app._register_sqlite_pragma()

    debug_mode = flask_app.config.get("DEBUG", False)
    socketio.run(
        flask_app,
        host="127.0.0.1",
        port=5000,
        debug=debug_mode,
        allow_unsafe_werkzeug=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
