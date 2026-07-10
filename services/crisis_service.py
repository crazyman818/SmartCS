"""危机干预服务 — 三级预警（黄/红）逻辑"""
from typing import Tuple
from flask_socketio import emit
from app import db, socketio
from repositories.data_access import UserRepository, ChatRepository

NEGATIVE_EMOTIONS = {"sad", "fear", "angry"}

EXTREME_KEYWORDS = [
    "不想活", "自杀", "死了算了", "活不下去", "不想活了",
    "报警", "投诉到媒体", "找记者", "曝光你们",
    "法院", "起诉", "律师", "12315", "315",
    "人身安全", "威胁", "要命",
]

YELLOW_CARE = ("我注意到您似乎有些情绪波动，我非常理解您的感受。"
               "请放心，我会尽我所能帮助您解决问题。")

RED_ALERT = ("我们非常重视您的情况。系统已暂停自动回复，"
             "人工客服正在紧急介入中，请稍等片刻。")


class CrisisService:
    """危机干预服务"""

    @staticmethod
    def update_risk_by_emotion(user, emotion: str, user_text: str = "") -> None:
        """按情绪更新风险状态"""
        if user_text and _has_extreme_keywords(user_text):
            user.risk_level = 'red'
            user.needs_intervention = True
            user.intervention_notified = False
            _push_alert(user, 'red', f'用户 {user.username} 触发极端关键词')
            return

        if user.needs_intervention:
            if emotion in NEGATIVE_EMOTIONS:
                user.risk_counter = min(user.risk_counter + 1, 9999)
            else:
                user.risk_counter = 0
            return

        if emotion in NEGATIVE_EMOTIONS:
            user.risk_counter += 1
        else:
            user.risk_counter = 0
            user.risk_level = 'normal'

        if user.risk_counter >= 3:
            recent = ChatRepository.get_recent_emotions(user.id, limit=5)
            recent.reverse()
            last_neg = [(r.emotion, r.confidence) for r in recent if r.emotion in NEGATIVE_EMOTIONS][-3:]
            if len(last_neg) >= 3 and sum(c for _, c in last_neg) / len(last_neg) > 0.7:
                user.risk_level = 'yellow'

            user.needs_intervention = True
            user.intervention_notified = False
            _push_alert(user, user.risk_level or 'normal',
                       f'用户 {user.username} ({user.risk_level}预警)，需要人工介入')

    @staticmethod
    def update_risk_by_feedback(user) -> None:
        """按反馈更新风险（连续两次踩）"""
        if user.needs_intervention:
            return

        recent = ChatRepository.get_recent_ai_replies(user.id, limit=2)
        if len(recent) >= 2 and all(r.feedback == -1 for r in recent):
            user.needs_intervention = True
            user.intervention_notified = False

    @staticmethod
    def resolve_user(user, admin) -> None:
        """解除干预状态"""
        user.needs_intervention = False
        user.risk_counter = 0
        user.intervention_notified = False
        db.session.add(user)

    @staticmethod
    def get_stats() -> dict:
        """危机统计数据"""
        return {
            "yellow": UserRepository.count_by_risk_level('yellow'),
            "red": UserRepository.count_by_risk_level('red'),
            "total": UserRepository.count_flagged(),
        }


def _has_extreme_keywords(text: str) -> bool:
    return any(kw in text for kw in EXTREME_KEYWORDS)


def _push_alert(user, risk_level: str, message: str):
    try:
        socketio.emit('crisis_alert', {
            'user_id': user.id, 'username': user.username,
            'risk_level': risk_level, 'message': message
        }, room='admin_room')
        socketio.emit('dashboard_update', {
            'type': 'crisis_intervention', 'user_id': user.id,
            'username': user.username, 'risk_level': risk_level,
            'needs_intervention': True
        }, room='admin_room')
    except Exception:
        pass
