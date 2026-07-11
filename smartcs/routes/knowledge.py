"""Admin knowledge-base route implementations."""
from __future__ import annotations

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from smartcs.extensions import db


def admin_kb_page():
    if not current_user.is_admin:
        return redirect(url_for("chat_page"))
    return render_template("admin_kb.html")


def api_admin_kb_qa_list():
    from smartcs.legacy_app import KnowledgeQA

    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    enabled = request.args.get("enabled", default="1")
    query = KnowledgeQA.query
    if enabled in ("0", "1"):
        query = query.filter_by(enabled=(enabled == "1"))
    rows = query.order_by(KnowledgeQA.updated_at.desc()).limit(500).all()

    data = []
    for row in rows:
        data.append(
            {
                "id": row.id,
                "question": row.question,
                "answer": row.answer,
                "tags": row.tags or "",
                "enabled": bool(row.enabled),
                "updated_at": row.updated_at.isoformat() if row.updated_at else "",
            }
        )
    return jsonify({"success": True, "data": data})


def api_admin_kb_qa_create():
    from smartcs.legacy_app import KnowledgeQA, kb_upsert_embedding_for_qa

    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    answer = (payload.get("answer") or "").strip()
    tags = (payload.get("tags") or "").strip()
    if len(question) < 2 or len(answer) < 2:
        return jsonify({"success": False, "msg": "question_and_answer_required"}), 400

    row = KnowledgeQA(question=question, answer=answer, tags=tags, enabled=True)
    kb_upsert_embedding_for_qa(row)
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True, "data": {"id": row.id}})


def api_admin_kb_qa_update(qid: int):
    from smartcs.legacy_app import KnowledgeQA, kb_upsert_embedding_for_qa

    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    row = db.session.get(KnowledgeQA, qid)
    if row is None:
        return jsonify({"success": False, "msg": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or row.question or "").strip()
    answer = (payload.get("answer") or row.answer or "").strip()
    tags = (payload.get("tags") or row.tags or "").strip()
    enabled = payload.get("enabled", row.enabled)

    if len(question) < 2 or len(answer) < 2:
        return jsonify({"success": False, "msg": "question_and_answer_required"}), 400

    row.question = question
    row.answer = answer
    row.tags = tags
    row.enabled = bool(enabled)
    kb_upsert_embedding_for_qa(row)
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True})


def api_admin_kb_qa_delete(qid: int):
    from smartcs.legacy_app import KnowledgeQA

    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    row = db.session.get(KnowledgeQA, qid)
    if row is None:
        return jsonify({"success": False, "msg": "not_found"}), 404

    row.enabled = False
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True})


def api_admin_kb_rebuild_embeddings():
    from smartcs.legacy_app import KnowledgeQA, kb_upsert_embedding_for_qa

    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    rows = KnowledgeQA.query.order_by(KnowledgeQA.id.asc()).all()
    updated = 0
    for row in rows:
        kb_upsert_embedding_for_qa(row)
        db.session.add(row)
        updated += 1
    db.session.commit()
    return jsonify({"success": True, "data": {"updated": updated}})


def register_knowledge_routes(app: Flask) -> None:
    """Point existing knowledge-base endpoints at the migrated route module."""
    app.view_functions["admin_kb_page"] = login_required(admin_kb_page)
    app.view_functions["api_admin_kb_qa_list"] = login_required(api_admin_kb_qa_list)
    app.view_functions["api_admin_kb_qa_create"] = login_required(api_admin_kb_qa_create)
    app.view_functions["api_admin_kb_qa_update"] = login_required(api_admin_kb_qa_update)
    app.view_functions["api_admin_kb_qa_delete"] = login_required(api_admin_kb_qa_delete)
    app.view_functions["api_admin_kb_rebuild_embeddings"] = login_required(api_admin_kb_rebuild_embeddings)