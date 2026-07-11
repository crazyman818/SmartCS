from tests.conftest import login


def test_chat_endpoints_are_served_from_chat_route_module(app):
    expected_module = "smartcs.routes.chat"

    assert app.view_functions["chat_page"].__module__ == expected_module
    assert app.view_functions["api_chat"].__module__ == expected_module


def test_admin_cannot_call_user_chat_api(client, users):
    response = login(client, "admin")
    assert response.status_code == 200

    response = client.post("/api/chat", json={"text": "hello"})

    assert response.status_code == 403
    assert response.get_json()["status"] == "forbidden"


def test_chat_api_rejects_empty_message(client, users):
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.post("/api/chat", json={"text": "   "})

    assert response.status_code == 400
    assert response.get_json()["status"] == "empty"

def test_chat_api_success_creates_user_and_reply_records(client, users):
    from smartcs import legacy_app

    response = login(client, "alice")
    assert response.status_code == 200

    response = client.post("/api/chat", json={"text": "你好"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert payload["user_record_id"]
    assert payload["record_id"]
    assert legacy_app.ChatRecord.query.count() == 2