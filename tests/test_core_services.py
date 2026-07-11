def test_classify_intent_recognizes_refund(app):
    from smartcs import legacy_app

    assert legacy_app.classify_intent("我要退款") == legacy_app.INTENT_REFUND


def test_llm_reply_falls_back_when_client_missing(app):
    from smartcs import legacy_app

    original_client = legacy_app.llm_client
    legacy_app.llm_client = None
    try:
        reply = legacy_app.generate_llm_reply("你好", "neutral")
    finally:
        legacy_app.llm_client = original_client

    assert "LLM_API_KEY" in reply


def test_crisis_service_flags_extreme_keyword(app, users):
    from services.crisis_service import CrisisService

    user = users["user"]
    CrisisService.update_risk_by_emotion(user, "neutral", "我要投诉到12315")

    assert user.needs_intervention is True
    assert user.risk_level == "red"
