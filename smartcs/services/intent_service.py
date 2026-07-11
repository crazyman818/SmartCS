"""Intent classification service."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentRule:
    intent: str
    keywords: tuple[str, ...]


class IntentService:
    """Keyword based intent classifier used by the Flask routes and tests."""

    def __init__(self, rules: list[IntentRule], default_intent: str):
        self.rules = rules
        self.default_intent = default_intent

    def classify(self, text: str) -> str:
        normalized = (text or "").strip().lower()
        if not normalized:
            return self.default_intent
        for rule in self.rules:
            if any(keyword.lower() in normalized for keyword in rule.keywords):
                return rule.intent
        return self.default_intent
