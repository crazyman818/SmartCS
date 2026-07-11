"""Customer chat route implementations."""
from __future__ import annotations

from typing import List

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from smartcs.extensions import db, limiter, socketio


def chat_page():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    return render_template("chat.html")


def api_chat():
    from smartcs.legacy_app import (
        CHAT_MAX_LEN,
        INTENT_ACCOUNT_GROUP,
        INTENT_COMPLAINT_GROUP,
        INTENT_GREETING_GROUP,
        INTENT_ORDER_GROUP,
        INTENT_PAYMENT_GROUP,
        INTENT_REFUND_GROUP,
        INTENT_TRANSFER_GROUP,
        ChatRecord,
        Order,
        admin_has_intervened,
        classify_intent,
        generate_llm_reply,
        kb_build_context,
        log_intent_stat,
        predict_emotion,
        update_risk_state_by_emotion,
    )

    if current_user.is_admin:
        return jsonify({"status": "forbidden", "message": "admin cannot use user chat api"}), 403

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or payload.get("message") or payload.get("input") or "").strip()
    if not text:
        return jsonify({"status": "empty"}), 400
    if len(text) > CHAT_MAX_LEN:
        return jsonify({"status": "error", "msg": f"消息过长，最多{CHAT_MAX_LEN}字"}), 400

    emotion, conf = predict_emotion(text)

    user_record = ChatRecord(
        user_id=current_user.id,
        text=text,
        reply="",
        emotion=emotion,
        confidence=conf,
        is_admin_reply=False,
    )
    db.session.add(user_record)

    update_risk_state_by_emotion(current_user, emotion, user_text=text)

    intent = classify_intent(text)
    log_intent_stat(intent, current_user.id)

    extra_system_info_parts: List[str] = []
    orders_data_for_frontend = []

    if intent in INTENT_ORDER_GROUP:
        user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.order_date.desc()).all()
        if user_orders:
            info_list = []
            for order in user_orders:
                arrival_str = order.estimated_arrival.strftime("%Y-%m-%d") if order.estimated_arrival else "待定"
                info_list.append(
                    f"单号:{order.order_number}, 商品:{order.item_name}, 状态:{order.status}, 预计:{arrival_str}"
                )
                orders_data_for_frontend.append(
                    {
                        "id": order.id,
                        "number": order.order_number,
                        "item": order.item_name,
                        "status": order.status,
                        "arrival": order.estimated_arrival.strftime("%m-%d") if order.estimated_arrival else "待定",
                    }
                )
            extra_system_info_parts.append("【用户订单信息】\n" + "\n".join(info_list))
        else:
            extra_system_info_parts.append("【用户订单信息】\n用户当前没有任何订单记录。")
    elif intent in INTENT_REFUND_GROUP:
        extra_system_info_parts.append(
            "【退款引导】用户询问退款相关事宜。请在回复中引导用户前往【个人中心】→【退款申请】提交退款工单。"
            "如已提交，告知用户可在【个人中心】→【退款列表】查看进度。审批通过后1-3个工作日原路退回。"
        )
    elif intent in INTENT_COMPLAINT_GROUP:
        extra_system_info_parts.append(
            "【投诉处理】用户表达强烈不满或投诉意图。请优先安抚情绪，表示歉意，"
            "并引导用户提供具体问题描述与订单号。告知将转交专人处理。"
        )
        if not current_user.needs_intervention:
            current_user.needs_intervention = True
            current_user.intervention_notified = False
    elif intent in INTENT_TRANSFER_GROUP:
        extra_system_info_parts.append(
            "【转人工请求】用户明确要求人工客服介入。请回复告知用户已记录请求，客服将尽快联系。"
        )
        if not current_user.needs_intervention:
            current_user.needs_intervention = True
            current_user.intervention_notified = False
    elif intent in INTENT_PAYMENT_GROUP:
        extra_system_info_parts.append(
            "【支付/发票】用户询问支付或发票相关问题。请在知识库中查询发票开具流程，"
            "或引导用户提供订单号以便核实支付状态。"
        )
    elif intent in INTENT_ACCOUNT_GROUP:
        extra_system_info_parts.append(
            "【账号管理】用户询问账号相关操作。密码修改可在【个人中心】操作，其他问题引导用户提供更多信息。"
        )
    elif intent in INTENT_GREETING_GROUP:
        extra_system_info_parts.append("【问候】用户在进行寒暄或表达感谢。请友好回应并询问是否需要帮助。")

    kb_ctx = kb_build_context(text, top_k=3)
    if kb_ctx:
        extra_system_info_parts.append(kb_ctx)

    extra_system_info = "\n\n".join([part for part in extra_system_info_parts if part.strip()])

    recent_history = (
        ChatRecord.query
        .filter_by(user_id=current_user.id)
        .filter(ChatRecord.id < user_record.id)
        .order_by(ChatRecord.id.desc())
        .limit(8)
        .all()
    )
    recent_history.reverse()

    reply_text = ""
    should_speak = True

    if current_user.needs_intervention:
        intervened = admin_has_intervened(current_user.id)
        if not intervened:
            if not current_user.intervention_notified:
                reply_text = "（⚠️ 检测到您情绪波动较大，已为您转接人工客服，请稍候。您也可以留下订单号与问题要点。）"
                current_user.intervention_notified = True
            else:
                reply_text = ""
                should_speak = False
        else:
            try:
                reply_text = generate_llm_reply(text, emotion, extra_system_info, recent_history)
            except Exception as exc:
                print(f"[ERROR] generate_llm_reply failed: {exc}")
                reply_text = "系统繁忙，请稍后重试。如需帮助请转人工客服。"
    else:
        try:
            reply_text = generate_llm_reply(text, emotion, extra_system_info, recent_history)
        except Exception as exc:
            print(f"[ERROR] generate_llm_reply failed: {exc}")
            reply_text = "系统繁忙，请稍后重试。如需帮助请转人工客服。"

    reply_record = ChatRecord(
        user_id=current_user.id,
        text="",
        reply=reply_text,
        emotion=emotion,
        confidence=conf,
        is_admin_reply=False,
        feedback=0,
    )
    db.session.add(reply_record)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f"[ERROR] api_chat db commit failed: {exc}")
        return jsonify({"status": "error", "message": "数据库写入失败，请稍后重试"}), 500

    socketio.emit(
        "new_message",
        {
            "id": reply_record.id,
            "reply": reply_text,
            "emotion": emotion,
            "confidence": conf,
            "timestamp": reply_record.timestamp.isoformat(),
            "is_admin_reply": False,
            "feedback": 0,
            "intervention": bool(current_user.needs_intervention),
            "should_speak": bool(should_speak and bool(reply_text)),
        },
        room=f"user_{current_user.id}",
    )

    return jsonify(
        {
            "status": "success",
            "emotion": emotion,
            "confidence": conf,
            "intervention": bool(current_user.needs_intervention),
            "should_speak": bool(should_speak and bool(reply_text)),
            "user_record_id": user_record.id,
            "record_id": reply_record.id,
            "reply": reply_text,
            "orders_data": orders_data_for_frontend,
        }
    )


def register_chat_routes(app: Flask) -> None:
    """Point existing customer chat endpoints at the migrated route module."""
    app.view_functions["chat_page"] = login_required(chat_page)
    app.view_functions["api_chat"] = login_required(limiter.limit("30 per minute")(api_chat))