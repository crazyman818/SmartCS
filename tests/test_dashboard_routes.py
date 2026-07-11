from tests.conftest import login


def test_dashboard_endpoints_are_served_from_dashboard_route_module(app):
    expected_module = "smartcs.routes.dashboard"

    assert app.view_functions["dashboard_page"].__module__ == expected_module
    assert app.view_functions["api_emotion_stats"].__module__ == expected_module
    assert app.view_functions["api_stats_summary"].__module__ == expected_module
    assert app.view_functions["api_emotion_daily_trend"].__module__ == expected_module
    assert app.view_functions["get_dashboard_data"].__module__ == expected_module


def test_non_admin_cannot_access_dashboard_apis(client, users):
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.get("/api/admin/stats_summary")
    assert response.status_code == 403
    assert response.get_json()["status"] == "forbidden"

    response = client.get("/api/emotion_daily_trend")
    assert response.status_code == 403
    assert response.get_json()["status"] == "forbidden"

    response = client.get("/api/admin/dashboard_data")
    assert response.status_code == 403
    assert response.get_json()["success"] is False


def test_admin_stats_summary_reports_core_metrics(client, users):
    from smartcs import legacy_app

    legacy_app.db.session.add(
        legacy_app.ChatRecord(
            user_id=users["user"].id,
            text="hello",
            reply="",
            emotion="happy",
            confidence=0.9,
            is_admin_reply=False,
            feedback=1,
        )
    )
    legacy_app.db.session.add(
        legacy_app.ChatRecord(
            user_id=users["user"].id,
            text="",
            reply="hi",
            emotion="happy",
            confidence=0.9,
            is_admin_reply=False,
        )
    )
    legacy_app.db.session.commit()

    response = login(client, "admin")
    assert response.status_code == 200

    response = client.get("/api/admin/stats_summary")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert payload["total_users"] == 1
    assert payload["total_messages"] == 1
    assert payload["satisfaction"] == 100.0
    assert payload["ai_replies"] == 1


def test_admin_dashboard_data_includes_user_intervention_status(client, users):
    users["user"].needs_intervention = True
    users["user"].risk_counter = 3
    from smartcs import legacy_app
    legacy_app.db.session.commit()

    response = login(client, "admin")
    assert response.status_code == 200

    response = client.get("/api/admin/dashboard_data")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["all_users"][0]["status"] == "needs_intervention"
    assert payload["flagged_users"] == [
        {"id": users["user"].id, "username": "alice", "risk_counter": 3}
    ]