"""Refund workflow route implementations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from smartcs.extensions import db


def api_refund_apply():
    from smartcs.legacy_app import Order, RefundRequest

    if current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    reason = (data.get("reason") or "").strip()

    if not reason:
        return jsonify({"status": "error", "msg": "请填写退款原因"}), 400

    if order_id:
        order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
        if not order:
            return jsonify({"status": "error", "msg": "订单不存在"}), 404
        if order.status == "已退款":
            return jsonify({"status": "error", "msg": "该订单已退款"}), 400

    refund = RefundRequest(
        user_id=current_user.id,
        order_id=order_id or None,
        reason=reason,
        status="待审核",
    )
    db.session.add(refund)
    db.session.commit()
    return jsonify(
        {
            "status": "success",
            "refund_id": refund.id,
            "msg": "退款申请已提交，等待客服审核",
        }
    )


def api_refund_list():
    from smartcs.legacy_app import RefundRequest

    if current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    refunds = (
        RefundRequest.query
        .filter_by(user_id=current_user.id)
        .order_by(RefundRequest.created_at.desc())
        .all()
    )
    result = []
    for refund in refunds:
        order_info = ""
        if refund.order:
            order_info = f"{refund.order.item_name}（{refund.order.order_number}）"
        result.append(
            {
                "id": refund.id,
                "order_info": order_info,
                "reason": refund.reason,
                "status": refund.status,
                "admin_note": refund.admin_note or "",
                "created_at": refund.created_at.strftime("%Y-%m-%d %H:%M") if refund.created_at else "",
            }
        )
    return jsonify({"status": "success", "refunds": result})


def api_admin_refunds():
    from smartcs.legacy_app import RefundRequest

    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    status_filter = request.args.get("status", "")
    query = RefundRequest.query.options(
        joinedload(RefundRequest.user), joinedload(RefundRequest.order)
    )
    if status_filter:
        query = query.filter_by(status=status_filter)
    refunds = query.order_by(RefundRequest.created_at.desc()).all()

    result = []
    for refund in refunds:
        order_info = ""
        if refund.order:
            order_info = f"{refund.order.item_name}（{refund.order.order_number}）"
        result.append(
            {
                "id": refund.id,
                "user_id": refund.user_id,
                "username": refund.user.username if refund.user else "",
                "order_info": order_info,
                "reason": refund.reason,
                "status": refund.status,
                "admin_note": refund.admin_note or "",
                "created_at": refund.created_at.strftime("%Y-%m-%d %H:%M") if refund.created_at else "",
                "updated_at": refund.updated_at.strftime("%Y-%m-%d %H:%M") if refund.updated_at else "",
            }
        )
    return jsonify({"status": "success", "refunds": result})


def api_admin_refund_update(rid: int):
    from smartcs.legacy_app import RefundRequest

    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    new_status = data.get("status", "")
    admin_note = (data.get("admin_note") or "").strip()

    if new_status not in ("已批准", "已拒绝"):
        return jsonify({"status": "error", "msg": "无效状态"}), 400

    refund = db.session.get(RefundRequest, rid)
    if refund is None:
        return jsonify({"status": "not_found"}), 404

    if refund.status in ("已批准", "已拒绝"):
        return jsonify({"status": "error", "msg": f"该退款工单状态为\"{refund.status}\"，不能重复审批"}), 400

    refund.status = new_status
    refund.admin_note = admin_note
    refund.updated_at = datetime.now(timezone.utc)

    if new_status == "已批准" and refund.order:
        refund.order.status = "已退款"

    db.session.commit()
    return jsonify({"status": "success"})


def admin_refund_page():
    if not current_user.is_admin:
        return redirect(url_for("chat_page"))
    return render_template("admin_refund.html")


def api_withdrawal_stats():
    """Return refund status counts for the admin dashboard."""
    from smartcs.legacy_app import RefundRequest

    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    total_refunds = RefundRequest.query.count()
    pending = RefundRequest.query.filter_by(status="待审核").count()
    approved = RefundRequest.query.filter_by(status="已批准").count()
    rejected = RefundRequest.query.filter_by(status="已拒绝").count()

    return jsonify(
        {
            "status": "success",
            "total_refunds": total_refunds,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
        }
    )


def api_refund_alert():
    """Return refund anomaly alert data for the admin dashboard."""
    from smartcs.legacy_app import Order, RefundRequest

    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    total_orders = Order.query.count()
    total_refunds = RefundRequest.query.count()
    pending = RefundRequest.query.filter_by(status="待审核").count()

    refund_rate = round(total_refunds / total_orders * 100, 1) if total_orders > 0 else 0.0

    alert_level = "normal"
    alert_message = ""
    if pending >= 10 or refund_rate >= 50.0:
        alert_level = "red"
        alert_message = f"退单红色预警：待审核{pending}笔，退款率{refund_rate}%。请立即安排人工处理！"
    elif pending >= 5 or refund_rate >= 30.0:
        alert_level = "yellow"
        alert_message = f"退单黄色预警：待审核{pending}笔，退款率{refund_rate}%。请关注退款趋势。"

    daily_refunds = []
    today = datetime.now(timezone.utc).date()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        count = RefundRequest.query.filter(
            RefundRequest.created_at >= day_start,
            RefundRequest.created_at < day_end,
        ).count()
        daily_refunds.append({"date": day.strftime("%m-%d"), "count": count})

    reason_stats = (
        db.session.query(RefundRequest.reason, db.func.count(RefundRequest.id))
        .group_by(RefundRequest.reason)
        .order_by(db.func.count(RefundRequest.id).desc())
        .limit(10)
        .all()
    )
    reasons = []
    for reason, count in reason_stats:
        reasons.append({"reason": (reason or "")[:50], "count": int(count)})

    return jsonify(
        {
            "status": "success",
            "alert_level": alert_level,
            "alert_message": alert_message,
            "total_orders": total_orders,
            "total_refunds": total_refunds,
            "pending": pending,
            "refund_rate": refund_rate,
            "daily_refunds": daily_refunds,
            "reason_distribution": reasons,
        }
    )
def register_refund_routes(app: Flask) -> None:
    """Point existing refund endpoints at the migrated route module."""
    app.view_functions["api_refund_apply"] = login_required(api_refund_apply)
    app.view_functions["api_refund_list"] = login_required(api_refund_list)
    app.view_functions["api_admin_refunds"] = login_required(api_admin_refunds)
    app.view_functions["api_admin_refund_update"] = login_required(api_admin_refund_update)
    app.view_functions["admin_refund_page"] = login_required(admin_refund_page)
    app.view_functions["api_withdrawal_stats"] = login_required(api_withdrawal_stats)
    app.view_functions["api_refund_alert"] = login_required(api_refund_alert)