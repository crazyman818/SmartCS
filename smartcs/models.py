"""SQLAlchemy model exports for SmartCS.

The model classes are re-exported from the compatibility module while routes are
being migrated into package blueprints.
"""
from smartcs.legacy_app import (
    ChatRecord,
    IntentStat,
    KnowledgeQA,
    Order,
    QuickReply,
    RefundRequest,
    User,
)

__all__ = [
    "ChatRecord",
    "IntentStat",
    "KnowledgeQA",
    "Order",
    "QuickReply",
    "RefundRequest",
    "User",
]
