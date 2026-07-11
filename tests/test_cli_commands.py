def test_cli_init_db_creates_schema(app):
    from smartcs import legacy_app

    runner = app.test_cli_runner()
    result = runner.invoke(args=["smartcs", "init-db"])

    assert result.exit_code == 0, result.output
    assert "Database initialized" in result.output
    assert legacy_app.User.query.count() == 0


def test_cli_seed_demo_creates_demo_accounts(app, monkeypatch):
    from smartcs import legacy_app

    monkeypatch.setenv("ENABLE_DEMO_SEED", "true")
    monkeypatch.setenv("DEMO_ADMIN_USERNAME", "demo-admin")
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "admin-password")
    monkeypatch.setenv("DEMO_USER_USERNAME", "demo-user")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "user-password")

    runner = app.test_cli_runner()
    result = runner.invoke(args=["smartcs", "seed-demo"])

    assert result.exit_code == 0, result.output
    assert "Demo data seeded" in result.output
    assert legacy_app.User.query.filter_by(username="demo-admin", is_admin=True).count() == 1
    assert legacy_app.User.query.filter_by(username="demo-user", is_admin=False).count() == 1


def test_cli_check_models_reports_missing_optional_model(app, monkeypatch):
    monkeypatch.setenv("LOAD_EMOTION_MODEL_ON_STARTUP", "false")

    runner = app.test_cli_runner()
    result = runner.invoke(args=["smartcs", "check-models"])

    assert result.exit_code == 0, result.output
    assert "Emotion model startup loading: disabled" in result.output
