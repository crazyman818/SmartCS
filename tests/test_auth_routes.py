def test_auth_endpoints_are_served_from_auth_route_module(app):
    expected_module = "smartcs.routes.auth"

    assert app.view_functions["index"].__module__ == expected_module
    assert app.view_functions["login"].__module__ == expected_module
    assert app.view_functions["logout"].__module__ == expected_module
    assert app.view_functions["register"].__module__ == expected_module


def test_register_json_creates_user_without_admin_privileges(client):
    from smartcs import legacy_app

    response = client.post(
        "/register",
        json={"username": "new-user", "password": "strong-password"},
    )

    assert response.status_code == 201
    assert response.get_json()["status"] == "success"

    user = legacy_app.User.query.filter_by(username="new-user").one()
    assert user.is_admin is False
    assert user.check_password("strong-password") is True