"""数据库访问层 — 对应 backend-patterns 的 Repository Pattern"""
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from smartcs.extensions import db
from smartcs.models import User, ChatRecord, Order, QuickReply, KnowledgeQA, RefundRequest, IntentStat


class ChatRepository:
    """聊天记录数据访问"""

    @staticmethod
    def create_user_message(user_id: int, text: str, emotion: str, confidence: float):
        record = ChatRecord(user_id=user_id, text=text, reply="", emotion=emotion,
                           confidence=confidence, is_admin_reply=False)
        db.session.add(record)
        return record

    @staticmethod
    def create_ai_reply(user_id: int, reply: str, emotion: str, confidence: float):
        record = ChatRecord(user_id=user_id, text="", reply=reply, emotion=emotion,
                           confidence=confidence, is_admin_reply=False, feedback=0)
        db.session.add(record)
        return record

    @staticmethod
    def create_admin_reply(user_id: int, reply: str):
        record = ChatRecord(user_id=user_id, text="", reply=reply, emotion="neutral",
                           confidence=0.0, is_admin_reply=True, feedback=0)
        db.session.add(record)
        return record

    @staticmethod
    def get_by_user(user_id: int, after_id: int = 0) -> List[ChatRecord]:
        return (ChatRecord.query
                .filter(ChatRecord.user_id == user_id, ChatRecord.id > after_id)
                .order_by(ChatRecord.id.asc()).all())

    @staticmethod
    def get_recent_history(user_id: int, before_id: int, limit: int = 8) -> List[ChatRecord]:
        return (ChatRecord.query
                .filter_by(user_id=user_id)
                .filter(ChatRecord.id < before_id)
                .order_by(ChatRecord.id.desc())
                .limit(limit).all())

    @staticmethod
    def get_by_id(record_id: int) -> Optional[ChatRecord]:
        return db.session.get(ChatRecord, record_id)

    @staticmethod
    def get_recent_emotions(user_id: int, limit: int = 5) -> List[ChatRecord]:
        return (ChatRecord.query
                .filter_by(user_id=user_id)
                .filter(ChatRecord.text != "", ChatRecord.emotion != "")
                .order_by(ChatRecord.id.desc())
                .limit(limit).all())

    @staticmethod
    def get_recent_ai_replies(user_id: int, limit: int = 2) -> List[ChatRecord]:
        return (ChatRecord.query
                .filter_by(user_id=user_id)
                .filter(ChatRecord.reply != "")
                .filter(ChatRecord.is_admin_reply.is_(False))
                .order_by(ChatRecord.id.desc())
                .limit(limit).all())

    @staticmethod
    def count_messages() -> int:
        return ChatRecord.query.filter(ChatRecord.text != '').count()

    @staticmethod
    def count_feedback(feedback_val: int) -> int:
        return ChatRecord.query.filter_by(feedback=feedback_val).count()

    @staticmethod
    def clear_user_history(user_id: int) -> bool:
        try:
            ChatRecord.query.filter_by(user_id=user_id).delete()
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    @staticmethod
    def get_all_with_username():
        from smartcs.models import User
        return (ChatRecord.query
                .join(User, ChatRecord.user_id == User.id)
                .add_columns(User.username)
                .order_by(ChatRecord.id.asc()).all())


class UserRepository:
    """用户数据访问"""

    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        return db.session.get(User, user_id)

    @staticmethod
    def get_by_username(username: str) -> Optional[User]:
        return User.query.filter_by(username=username).first()

    @staticmethod
    def get_non_admins() -> List[User]:
        return User.query.filter_by(is_admin=False).order_by(User.id.desc()).all()

    @staticmethod
    def get_flagged_users() -> List[User]:
        return User.query.filter_by(needs_intervention=True, is_admin=False).order_by(
            User.risk_counter.desc()).all()

    @staticmethod
    def count_non_admins() -> int:
        return User.query.filter_by(is_admin=False).count()

    @staticmethod
    def count_flagged() -> int:
        return User.query.filter_by(is_admin=False, needs_intervention=True).count()

    @staticmethod
    def count_by_risk_level(level: str) -> int:
        return User.query.filter_by(is_admin=False, risk_level=level, needs_intervention=True).count()

    @staticmethod
    def save(user: User):
        db.session.add(user)


class OrderRepository:
    @staticmethod
    def get_by_user(user_id: int) -> List[Order]:
        return Order.query.filter_by(user_id=user_id).order_by(Order.order_date.desc()).all()

    @staticmethod
    def get_by_id(order_id: int) -> Optional[Order]:
        return db.session.get(Order, order_id)

    @staticmethod
    def count_all() -> int:
        return Order.query.count()


class QuickReplyRepository:
    @staticmethod
    def get_all() -> List[QuickReply]:
        return QuickReply.query.order_by(QuickReply.id.desc()).all()

    @staticmethod
    def get_by_id(qid: int) -> Optional[QuickReply]:
        return db.session.get(QuickReply, qid)

    @staticmethod
    def create(content: str) -> QuickReply:
        q = QuickReply(content=content)
        db.session.add(q)
        return q

    @staticmethod
    def delete(q: QuickReply):
        db.session.delete(q)


class KnowledgeQARepository:
    @staticmethod
    def get_all(enabled_only: bool = True) -> List[KnowledgeQA]:
        q = KnowledgeQA.query.order_by(KnowledgeQA.updated_at.desc())
        if enabled_only:
            q = q.filter_by(enabled=True)
        return q.limit(500).all()

    @staticmethod
    def get_by_id(qid: int) -> Optional[KnowledgeQA]:
        return db.session.get(KnowledgeQA, qid)

    @staticmethod
    def create(question: str, answer: str, tags: str = "", category: str = "") -> KnowledgeQA:
        row = KnowledgeQA(question=question, answer=answer, tags=tags, category=category, enabled=True)
        db.session.add(row)
        return row

    @staticmethod
    def save(row: KnowledgeQA):
        db.session.add(row)


class RefundRepository:
    @staticmethod
    def get_by_user(user_id: int) -> List[RefundRequest]:
        return (RefundRequest.query.filter_by(user_id=user_id)
                .order_by(RefundRequest.created_at.desc()).all())

    @staticmethod
    def get_all(status: str = "") -> List[RefundRequest]:
        q = RefundRequest.query
        if status:
            q = q.filter_by(status=status)
        return q.order_by(RefundRequest.created_at.desc()).all()

    @staticmethod
    def get_by_id(rid: int) -> Optional[RefundRequest]:
        return db.session.get(RefundRequest, rid)

    @staticmethod
    def count_by_status(status: str) -> int:
        return RefundRequest.query.filter_by(status=status).count()

    @staticmethod
    def count_all() -> int:
        return RefundRequest.query.count()

    @staticmethod
    def create(user_id: int, reason: str, order_id: int = None) -> RefundRequest:
        refund = RefundRequest(user_id=user_id, order_id=order_id, reason=reason, status='待审核')
        db.session.add(refund)
        return refund


class IntentStatRepository:
    @staticmethod
    def log(intent: str, user_id: int):
        stat = IntentStat(intent=intent, user_id=user_id)
        db.session.add(stat)

    @staticmethod
    def get_distribution():
        return (db.session.query(IntentStat.intent, db.func.count(IntentStat.id))
                .group_by(IntentStat.intent)
                .order_by(db.func.count(IntentStat.id).desc()).all())

    @staticmethod
    def count_total() -> int:
        return db.session.query(IntentStat).count()
