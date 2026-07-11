import importlib
import os
import sys

import pytest


@pytest.fixture()
def app():
    os.environ["SMARTCS_ENV"] = "testing"
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["SOCKETIO_ASYNC_MODE"] = "threading"


    smartcs = importlib.import_module("smartcs")
    flask_app = smartcs.create_app("testing")

    from smartcs import legacy_app

    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_CHECK_DEFAULT=False,
        LOAD_EMOTION_MODEL_ON_STARTUP=False,
        ENABLE_DEMO_SEED=False,
        RATELIMIT_ENABLED=False,
    )

    with flask_app.app_context():
        legacy_app.db.drop_all()
        legacy_app.db.create_all()
        yield flask_app
        legacy_app.db.session.remove()
        legacy_app.db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def users(app):
    from smartcs import legacy_app

    admin = legacy_app.User(username="admin", is_admin=True)
    admin.set_password("password123")
    user = legacy_app.User(username="alice", is_admin=False)
    user.set_password("password123")
    legacy_app.db.session.add_all([admin, user])
    legacy_app.db.session.commit()
    return {"admin": admin, "user": user}


def login(client, username="alice", password="password123"):
    return client.post(
        "/login",
        json={"username": username, "password": password},
    )
