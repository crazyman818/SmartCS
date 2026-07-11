from tests.conftest import login


def test_create_app_uses_testing_config(app):
    assert app.testing is True
    assert app.config["LOAD_EMOTION_MODEL_ON_STARTUP"] is False


def test_non_admin_cannot_access_admin_api(client, users):
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.get("/api/admin/dashboard_data")
    assert response.status_code == 403


def test_admin_can_access_dashboard_api(client, users):
    response = login(client, "admin")
    assert response.status_code == 200

    response = client.get("/api/admin/dashboard_data")
    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_user_socket_cannot_join_another_user_room(app, users):
    from smartcs.extensions import socketio

    client = app.test_client()
    login(client, "alice")
    socket_client = socketio.test_client(app, flask_test_client=client)

    socket_client.emit("join", {"type": "user", "user_id": users["admin"].id})
    received = socket_client.get_received()

    assert any(event["name"] == "joined" for event in received)
    joined_payload = next(event["args"][0] for event in received if event["name"] == "joined")
    assert joined_payload["status"] == "error"


def test_user_socket_cannot_join_admin_room(app, users):
    from smartcs.extensions import socketio

    client = app.test_client()
    login(client, "alice")
    socket_client = socketio.test_client(app, flask_test_client=client)

    socket_client.emit("join", {"type": "admin"})
    joined_payload = next(event["args"][0] for event in socket_client.get_received() if event["name"] == "joined")

    assert joined_payload["status"] == "error"


def test_socketio_polling_accepts_configured_local_origin(app):
    response = app.test_client().get(
        "/socket.io/?EIO=4&transport=polling&t=test-origin",
        headers={"Origin": "http://127.0.0.1:5000"},
    )

    assert response.status_code == 200
    assert b'"sid"' in response.data