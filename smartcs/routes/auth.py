"""Authentication route implementations."""
from __future__ import annotations

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from smartcs.extensions import db, limiter


def index():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("chat_page"))


def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("chat_page"))

    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True, silent=True) or {}
            username = (data.get("username") or "").strip()
            password = data.get("password") or ""
        else:
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""

        from smartcs.legacy_app import User

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            if request.is_json:
                return jsonify({"status": "success", "msg": "登录成功", "is_admin": user.is_admin}), 200
            if user.is_admin:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("chat_page"))

        if request.is_json:
            return jsonify({"status": "error", "msg": "用户名或密码错误"}), 401
        flash("用户名或密码错误", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat_page"))

    if request.method == "POST":
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            username = (payload.get("username") or "").strip()
            password = (payload.get("password") or "").strip()
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

        from smartcs.legacy_app import PW_MIN_LEN, User

        if not username or not password:
            if request.is_json:
                return jsonify({"status": "error", "msg": "用户名或密码不能为空"}), 400
            return render_template("register.html", error="用户名或密码不能为空")

        if len(username) < 2 or len(username) > 30:
            if request.is_json:
                return jsonify({"status": "error", "msg": "用户名长度需在 2~30 个字符之间"}), 400
            return render_template("register.html", error="用户名长度需在 2~30 个字符之间")

        if len(password) < PW_MIN_LEN:
            if request.is_json:
                return jsonify({"status": "error", "msg": f"密码不能少于{PW_MIN_LEN}位"}), 400
            return render_template("register.html", error=f"密码不能少于{PW_MIN_LEN}位")

        if User.query.filter_by(username=username).first():
            if request.is_json:
                return jsonify({"status": "error", "msg": "该用户名已被占用"}), 409
            return render_template("register.html", error="该用户名已被占用")

        new_user = User(username=username, is_admin=False)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        if request.is_json:
            return jsonify({"status": "success", "msg": "注册成功，请登录"}), 201
        return redirect(url_for("login", msg="注册成功，请登录"))

    return render_template("register.html")


def register_auth_routes(app: Flask) -> None:
    """Point existing auth endpoints at the migrated route module."""
    app.view_functions["index"] = index
    app.view_functions["login"] = limiter.limit("10 per minute")(login)
    app.view_functions["logout"] = logout
    app.view_functions["register"] = limiter.limit("5 per minute")(register)