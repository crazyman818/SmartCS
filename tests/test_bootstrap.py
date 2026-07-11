def test_bootstrap_application_runs_startup_tasks_in_order(app, monkeypatch):
    from smartcs import legacy_app
    from smartcs.bootstrap import bootstrap_application

    calls = []

    monkeypatch.setattr(legacy_app.db, "create_all", lambda: calls.append("create_all"))
    monkeypatch.setattr(legacy_app, "_ensure_indexes", lambda: calls.append("ensure_indexes"))
    monkeypatch.setattr(legacy_app, "seed_defaults", lambda: calls.append("seed_defaults"))
    monkeypatch.setattr(legacy_app, "load_emotion_model", lambda: calls.append("load_emotion_model"))
    monkeypatch.setattr(legacy_app, "_register_sqlite_pragma", lambda: calls.append("register_pragma"))

    app.config["LOAD_EMOTION_MODEL_ON_STARTUP"] = True

    bootstrap_application(app)

    assert calls == [
        "create_all",
        "ensure_indexes",
        "seed_defaults",
        "load_emotion_model",
        "register_pragma",
    ]


def test_bootstrap_application_can_skip_seed_and_model_loading(app, monkeypatch):
    from smartcs import legacy_app
    from smartcs.bootstrap import bootstrap_application

    calls = []

    monkeypatch.setattr(legacy_app.db, "create_all", lambda: calls.append("create_all"))
    monkeypatch.setattr(legacy_app, "_ensure_indexes", lambda: calls.append("ensure_indexes"))
    monkeypatch.setattr(legacy_app, "seed_defaults", lambda: calls.append("seed_defaults"))
    monkeypatch.setattr(legacy_app, "load_emotion_model", lambda: calls.append("load_emotion_model"))
    monkeypatch.setattr(legacy_app, "_register_sqlite_pragma", lambda: calls.append("register_pragma"))

    app.config["LOAD_EMOTION_MODEL_ON_STARTUP"] = True

    bootstrap_application(app, seed_demo=False, load_model=False)

    assert calls == [
        "create_all",
        "ensure_indexes",
        "register_pragma",
    ]
