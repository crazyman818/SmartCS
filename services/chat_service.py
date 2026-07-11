"""聊天服务层 — 对应 backend-patterns 的 Service Layer Pattern"""
from typing import Optional, Tuple, List, Dict, Any
from flask_socketio import emit as socket_emit
from smartcs.extensions import db, socketio
from repositories.data_access import ChatRepository, UserRepository, KnowledgeQARepository
from utils.errors import ValidationError


class ChatService:
    """聊天消息处理服务"""

    @staticmethod
    def process_message(user, text: str, emotion: str, confidence: float,
                        intent: str, kb_context: str, orders_data: list) -> dict:
        """处理一条用户消息的完整流程（不含 LLM 生成，由调用方提供）"""
        from smartcs.legacy_app import classify_intent, log_intent_stat, update_risk_state_by_emotion

        # 1. 写入用户消息
        user_record = ChatRepository.create_user_message(user.id, text, emotion, confidence)

        # 2. 更新危机状态
        update_risk_state_by_emotion(user, emotion, user_text=text)

        # 3. 意图分类与统计
        log_intent_stat(intent, user.id)

        # 4. 构建系统上下文
        extra_info_parts = []
        if intent == 'order_query' or intent == 'logistics' or intent == 'order_received':
            orders = _build_order_info(user.id)
            orders_data.extend(orders)
            if orders:
                info_list = [f"单号:{o['number']}, 商品:{o['item']}, 状态:{o['status']}"
                           for o in orders]
                extra_info_parts.append("【用户订单信息】\n" + "\n".join(info_list))
            else:
                extra_info_parts.append("【用户订单信息】\n用户当前没有任何订单记录。")
        elif intent in ('refund', 'return_exchange'):
            extra_info_parts.append(_REFUND_GUIDE)
        elif intent in ('complaint', 'product_quality'):
            extra_info_parts.append(_COMPLAINT_GUIDE)
            if not user.needs_intervention:
                user.needs_intervention = True
                user.intervention_notified = False
        elif intent == 'transfer_human':
            extra_info_parts.append(_TRANSFER_GUIDE)
            if not user.needs_intervention:
                user.needs_intervention = True
                user.intervention_notified = False
        elif intent in ('payment', 'invoice', 'price'):
            extra_info_parts.append(_PAYMENT_GUIDE)
        elif intent == 'account':
            extra_info_parts.append(_ACCOUNT_GUIDE)
        elif intent in ('greeting', 'chitchat'):
            extra_info_parts.append(_GREETING_GUIDE)

        # 5. RAG 知识库上下文
        if kb_context:
            extra_info_parts.append(kb_context)

        extra_system_info = "\n\n".join([p for p in extra_info_parts if p.strip()])
        return {
            "user_record": user_record,
            "extra_system_info": extra_system_info,
        }

    @staticmethod
    def build_reply_with_intervention(user, text: str, emotion: str,
                                       extra_info: str, history: list) -> Tuple[str, bool]:
        """生成回复（含危机干预沉默逻辑）"""
        from smartcs.legacy_app import generate_llm_reply, admin_has_intervened

        if not user.needs_intervention:
            reply = generate_llm_reply(text, emotion, extra_info, history)
            return reply, True

        intervened = admin_has_intervened(user.id)
        if intervened:
            reply = generate_llm_reply(text, emotion, extra_info, history)
            return reply, True

        if not user.intervention_notified:
            user.intervention_notified = True
            return "（⚠️ 检测到您情绪波动较大，已为您转接人工客服，请稍候。您也可以留下订单号与问题要点。）", True

        return "", False

    @staticmethod
    def save_reply(user_id: int, reply_text: str, emotion: str, confidence: float):
        return ChatRepository.create_ai_reply(user_id, reply_text, emotion, confidence)

    @staticmethod
    def get_messages_for_user(user_id: int, after_id: int = 0) -> list:
        records = ChatRepository.get_by_user(user_id, after_id)
        return [_record_to_dict(r) for r in records]

    @staticmethod
    def get_messages_for_admin(user_id: int, after_id: int = 0) -> list:
        return ChatService.get_messages_for_user(user_id, after_id)

    @staticmethod
    def process_feedback(user, record_id: int, action: str) -> bool:
        """处理用户反馈（赞/踩），返回是否触发干预"""
        from smartcs.legacy_app import update_risk_state_by_feedback

        record = ChatRepository.get_by_id(record_id)
        if not record or record.user_id != user.id:
            raise ValidationError("记录不存在")
        if not record.reply or record.is_admin_reply:
            raise ValidationError("该消息不支持反馈")

        record.feedback = 1 if action == "like" else -1
        db.session.add(record)
        db.session.commit()

        update_risk_state_by_feedback(user)
        db.session.commit()
        return user.needs_intervention

    @staticmethod
    def send_admin_reply(admin_user, target_user_id: int, reply_text: str):
        """管理员发送人工回复"""
        target = UserRepository.get_by_id(target_user_id)
        if not target:
            raise ValidationError("用户不存在")

        record = ChatRepository.create_admin_reply(target_user_id, reply_text)
        db.session.commit()

        # WebSocket 推送
        _ws_push(f'user_{target_user_id}', 'new_message', {
            'id': record.id, 'reply': reply_text, 'emotion': 'neutral',
            'confidence': 0.0, 'timestamp': record.timestamp.isoformat(),
            'is_admin_reply': True, 'feedback': 0, 'intervention': False,
            'should_speak': True,
        })
        _ws_push('admin_room', 'admin_notification', {
            'type': 'new_admin_reply', 'user_id': target.id,
            'username': target.username, 'message': '用户收到人工回复'
        })
        return record


# ===== 私有工具函数 =====

def _build_order_info(user_id: int) -> list:
    """构建订单信息列表"""
    from repositories.data_access import OrderRepository
    orders = OrderRepository.get_by_user(user_id)
    result = []
    for o in orders:
        arrival = o.estimated_arrival.strftime('%Y-%m-%d') if o.estimated_arrival else "待定"
        result.append({"id": o.id, "number": o.order_number, "item": o.item_name,
                       "status": o.status, "arrival": o.estimated_arrival.strftime('%m-%d') if o.estimated_arrival else "待定"})
    return result


def _ws_push(room: str, event: str, data: dict):
    """安全推送 WebSocket"""
    try:
        socketio.emit(event, data, room=room)
    except Exception:
        pass


def _record_to_dict(r) -> dict:
    return {"id": r.id, "text": r.text, "reply": r.reply,
            "emotion": r.emotion, "confidence": r.confidence,
            "timestamp": r.timestamp.isoformat(), "is_admin_reply": bool(r.is_admin_reply),
            "feedback": int(r.feedback or 0), "rating": int(r.rating or 0)}


# 意图回复模板
_REFUND_GUIDE = ("【退款引导】用户询问退款相关事宜。请在回复中引导用户前往【个人中心】→【退款申请】"
                  "提交退款工单。如已提交，告知用户可在【个人中心】→【退款列表】查看进度。")
_COMPLAINT_GUIDE = ("【投诉处理】用户表达强烈不满或投诉意图。请优先安抚情绪，表示歉意，"
                    "并引导用户提供具体问题描述与订单号。")
_TRANSFER_GUIDE = "【转人工请求】用户明确要求人工客服介入。请回复告知用户已记录请求，客服将尽快联系。"
_PAYMENT_GUIDE = "【支付/发票】用户询问支付或发票相关问题。请在知识库中查询发票开具流程。"
_ACCOUNT_GUIDE = "【账号管理】用户询问账号相关操作。密码修改可在【个人中心】操作。"
_GREETING_GUIDE = "【问候】用户在进行寒暄或表达感谢。请友好回应并询问是否需要帮助。"
