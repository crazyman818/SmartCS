from tests.conftest import login


def _create_order(user_id):
    from smartcs import legacy_app

    order = legacy_app.Order(
        user_id=user_id,
        order_number=f"OD-TEST-{user_id}",
        item_name="Test Keyboard",
        status="已发货",
    )
    legacy_app.db.session.add(order)
    legacy_app.db.session.commit()
    return order


def _create_refund(user_id, order_id=None, reason="质量问题"):
    from smartcs import legacy_app

    refund = legacy_app.RefundRequest(
        user_id=user_id,
        order_id=order_id,
        reason=reason,
        status="待审核",
    )
    legacy_app.db.session.add(refund)
    legacy_app.db.session.commit()
    return refund


def test_refund_endpoints_are_served_from_refund_route_module(app):
    expected_module = "smartcs.routes.refunds"

    assert app.view_functions["api_refund_apply"].__module__ == expected_module
    assert app.view_functions["api_refund_list"].__module__ == expected_module
    assert app.view_functions["api_admin_refunds"].__module__ == expected_module
    assert app.view_functions["api_admin_refund_update"].__module__ == expected_module
    assert app.view_functions["admin_refund_page"].__module__ == expected_module


def test_user_can_apply_for_refund_on_own_order(client, users):
    from smartcs import legacy_app

    order = _create_order(users["user"].id)
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.post(
        "/api/refund/apply",
        json={"order_id": order.id, "reason": "商品有质量问题"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    refund = legacy_app.db.session.get(legacy_app.RefundRequest, payload["refund_id"])
    assert refund.user_id == users["user"].id
    assert refund.order_id == order.id
    assert refund.status == "待审核"


def test_user_refund_list_only_returns_own_refunds(client, users):
    _create_refund(users["user"].id, reason="我的退款")
    _create_refund(users["admin"].id, reason="其他人的退款")
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.get("/api/refund/list")

    assert response.status_code == 200
    refunds = response.get_json()["refunds"]
    assert [item["reason"] for item in refunds] == ["我的退款"]


def test_non_admin_cannot_list_admin_refunds(client, users):
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.get("/api/admin/refunds")

    assert response.status_code == 403
    assert response.get_json()["status"] == "forbidden"


def test_admin_can_approve_refund_and_mark_order_refunded(client, users):
    from smartcs import legacy_app

    order = _create_order(users["user"].id)
    refund = _create_refund(users["user"].id, order_id=order.id)
    response = login(client, "admin")
    assert response.status_code == 200

    response = client.post(
        f"/api/admin/refund/{refund.id}/update",
        json={"status": "已批准", "admin_note": "同意退款"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    assert refund.status == "已批准"
    assert refund.admin_note == "同意退款"
    assert order.status == "已退款"

def test_refund_analytics_endpoints_are_served_from_refund_route_module(app):
    expected_module = "smartcs.routes.refunds"

    assert app.view_functions["api_withdrawal_stats"].__module__ == expected_module
    assert app.view_functions["api_refund_alert"].__module__ == expected_module


def test_non_admin_cannot_access_refund_analytics(client, users):
    response = login(client, "alice")
    assert response.status_code == 200

    response = client.get("/api/withdrawal_stats")
    assert response.status_code == 403
    assert response.get_json()["status"] == "forbidden"

    response = client.get("/api/refund_alert")
    assert response.status_code == 403
    assert response.get_json()["status"] == "forbidden"


def test_admin_refund_alert_reports_pending_refund_metrics(client, users):
    order = _create_order(users["user"].id)
    _create_refund(users["user"].id, order_id=order.id, reason="质量问题")
    response = login(client, "admin")
    assert response.status_code == 200

    response = client.get("/api/refund_alert")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert payload["total_orders"] == 1
    assert payload["total_refunds"] == 1
    assert payload["pending"] == 1
    assert payload["reason_distribution"] == [{"reason": "质量问题", "count": 1}]