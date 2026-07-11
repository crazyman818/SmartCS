"""Container entrypoint for SmartCS."""
from smartcs import create_app
from smartcs.bootstrap import bootstrap_application
from smartcs.extensions import socketio


def main() -> None:
    flask_app = create_app()
    bootstrap_application(flask_app)

    socketio.run(
        flask_app,
        host="0.0.0.0",
        port=5000,
        debug=flask_app.config.get("DEBUG", False),
        allow_unsafe_werkzeug=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()