"""WSGI/Socket.IO entrypoint for production servers."""
from smartcs import create_app
from smartcs.extensions import socketio

app = create_app()
