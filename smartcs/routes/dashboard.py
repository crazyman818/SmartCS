"""Admin dashboard route implementations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from smartcs.extensions import db


def dashboard_page():
    if not current_user.is_admin:
        return redirect(url_for("chat_page"))
    return render_template("dashboard.html")


def api_emotion_stats():
    from smartcs.legacy_app import ChatRecord

    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    results = (
        db.session.query(ChatRecord.emotion, db.func.count(ChatRecord.emotion))
        .filter(ChatRecord.emotion != None)  # noqa: E711
        .group_by(ChatRecord.emotion)
        .all()
    )
    stats = {emotion: int(count) for (emotion, count) in results if emotion}
    return jsonify({"status": "success", "stats": stats})


def api_stats_summary():
    from smartcs.legacy_app import ChatRecord, RefundRequest, User

    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    total_users = User.query.filter_by(is_admin=False).count()
    total_messages = ChatRecord.query.filter(ChatRecord.text != "").count()

    total_feedback = ChatRecord.query.filter(ChatRecord.feedback != 0).count()
    likes = ChatRecord.query.filter_by(feedback=1).count()
    satisfaction = round(likes / total_feedback * 100, 1) if total_feedback > 0 else 0.0

    intervention_users = User.query.filter_by(is_admin=False, needs_intervention=True).count()
    intervention_rate = round(intervention_users / total_users * 100, 1) if total_users > 0 else 0.0

    ai_replies = ChatRecord.query.filter(
        ChatRecord.reply != "", ChatRecord.is_admin_reply.is_(False)
    ).count()
    admin_replies = ChatRecord.query.filter_by(is_admin_reply=True).count()

    daily_data = []
    today = datetime.now(timezone.utc).date()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = ChatRecord.query.filter(
            ChatRecord.timestamp >= day_start,
            ChatRecord.timestamp < day_end,
            ChatRecord.text != "",
        ).count()
        daily_data.append({"date": day.strftime("%m-%d"), "count": count})

    refund_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = RefundRequest.query.filter(
            RefundRequest.created_at >= day_start,
            RefundRequest.created_at < day_end,
        ).count()
        refund_data.append({"date": day.strftime("%m-%d"), "count": count})

    pending_refunds = RefundRequest.query.filter_by(status="待审核").count()

    return jsonify(
        {
            "status": "success",
            "total_users": total_users,
            "total_messages": total_messages,
            "satisfaction": satisfaction,
            "intervention_rate": intervention_rate,
            "intervention_users": intervention_users,
            "ai_replies": ai_replies,
            "admin_replies": admin_replies,
            "pending_refunds": pending_refunds,
            "daily_messages": daily_data,
            "daily_refunds": refund_data,
        }
    )


def api_emotion_daily_trend():
    from smartcs.legacy_app import ChatRecord

    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    emotions = ["neutral", "happy", "angry", "sad", "fear", "surprise"]
    today = datetime.now(timezone.utc).date()
    daily_emotions = []

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        day_data = {"date": day.strftime("%m-%d")}
        for emotion in emotions:
            count = ChatRecord.query.filter(
                ChatRecord.timestamp >= day_start,
                ChatRecord.timestamp < day_end,
                ChatRecord.emotion == emotion,
                ChatRecord.text != "",
            ).count()
            day_data[emotion] = count
        daily_emotions.append(day_data)

    return jsonify({"status": "success", "daily_emotions": daily_emotions})


def get_dashboard_data():
    from smartcs.legacy_app import User

    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "无权限"}), 403

    users = User.query.filter_by(is_admin=False).all()
    all_users_data = []
    for user in users:
        status = "needs_intervention" if user.needs_intervention else "normal"
        all_users_data.append(
            {
                "id": user.id,
                "username": user.username,
                "status": status,
                "needs_intervention": user.needs_intervention,
                "persona_tags": user.persona_tags or "",
                "persona_summary": user.persona_summary or "",
                "last_analyzed": user.last_analyzed.strftime("%Y-%m-%d %H:%M:%S") if user.last_analyzed else "",
            }
        )

    flagged = [user for user in users if user.needs_intervention]
    flagged_data = [
        {"id": user.id, "username": user.username, "risk_counter": user.risk_counter}
        for user in flagged
    ]

    return jsonify({"success": True, "all_users": all_users_data, "flagged_users": flagged_data})


def register_dashboard_routes(app: Flask) -> None:
    """Point existing dashboard endpoints at the migrated route module."""
    app.view_functions["dashboard_page"] = login_required(dashboard_page)
    app.view_functions["api_emotion_stats"] = login_required(api_emotion_stats)
    app.view_functions["api_stats_summary"] = login_required(api_stats_summary)
    app.view_functions["api_emotion_daily_trend"] = login_required(api_emotion_daily_trend)
    app.view_functions["get_dashboard_data"] = login_required(get_dashboard_data)