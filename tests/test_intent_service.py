from smartcs.services.intent_service import IntentRule, IntentService


def test_intent_service_returns_default_for_empty_text():
    service = IntentService([IntentRule("refund", ("退款",))], default_intent="chitchat")

    assert service.classify("") == "chitchat"


def test_intent_service_matches_keyword():
    service = IntentService([IntentRule("refund", ("退款",))], default_intent="chitchat")

    assert service.classify("我想申请退款") == "refund"
