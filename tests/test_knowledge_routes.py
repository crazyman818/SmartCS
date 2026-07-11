from tests.conftest import login


def test_knowledge_endpoints_are_served_from_knowledge_route_module(app):
    expected_module = "smartcs.routes.knowledge"

    assert app.view_functions["admin_kb_page"].__module__ == expected_module
    assert app.view_functions["api_admin_kb_qa_list"].__module__ == expected_module
    assert app.view_functions["api_admin_kb_qa_create"].__module__ == expected_module
    assert app.view_functions["api_admin_kb_qa_update"].__module__ == expected_module
    assert app.view_functions["api_admin_kb_qa_delete"].__module__ == expected_module
    assert app.view_functions["api_admin_kb_rebuild_embeddings"].__module__ == expected_module


def test_non_admin_cannot_manage_knowledge_base(client, users):
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.get("/api/admin/kb/qa/list")
    assert response.status_code == 403
    assert response.get_json() == {"success": False, "msg": "forbidden"}

    response = client.post(
        "/api/admin/kb/qa/create",
        json={"question": "refund", "answer": "contact support"},
    )
    assert response.status_code == 403
    assert response.get_json() == {"success": False, "msg": "forbidden"}


def test_admin_can_create_update_list_delete_and_rebuild_knowledge_items(client, users):
    from smartcs import legacy_app

    response = login(client, "admin")
    assert response.status_code == 200

    response = client.post(
        "/api/admin/kb/qa/create",
        json={"question": "How do refunds work?", "answer": "Use the refund center.", "tags": "refund"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    qid = payload["data"]["id"]

    row = legacy_app.db.session.get(legacy_app.KnowledgeQA, qid)
    assert row.question == "How do refunds work?"
    assert row.answer == "Use the refund center."
    assert row.tags == "refund"
    assert row.enabled is True

    response = client.get("/api/admin/kb/qa/list?enabled=1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"][0]["id"] == qid
    assert payload["data"][0]["question"] == "How do refunds work?"

    response = client.post(
        f"/api/admin/kb/qa/{qid}/update",
        json={"question": "Refund window?", "answer": "Refunds are reviewed by admins.", "enabled": False},
    )
    assert response.status_code == 200
    assert response.get_json() == {"success": True}

    row = legacy_app.db.session.get(legacy_app.KnowledgeQA, qid)
    assert row.question == "Refund window?"
    assert row.answer == "Refunds are reviewed by admins."
    assert row.enabled is False

    response = client.post(f"/api/admin/kb/qa/{qid}/delete")
    assert response.status_code == 200
    assert response.get_json() == {"success": True}
    assert legacy_app.db.session.get(legacy_app.KnowledgeQA, qid).enabled is False

    response = client.post("/api/admin/kb/rebuild_embeddings")
    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": {"updated": 1}}


def test_admin_knowledge_create_rejects_short_content(client, users):
    response = login(client, "admin")
    assert response.status_code == 200

    response = client.post(
        "/api/admin/kb/qa/create",
        json={"question": "?", "answer": "x"},
    )

    assert response.status_code == 400
    assert response.get_json()["success"] is False