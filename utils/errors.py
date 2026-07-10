"""集中化异常处理 — 对应 backend-patterns 的 Centralized Error Handler"""
from typing import Optional, Any, Dict
from flask import jsonify


class AppError(Exception):
    """应用级异常基类"""
    def __init__(self, message: str, status_code: int = 400, data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.data = data or {}

    def to_response(self):
        return jsonify({"success": False, "msg": self.message, **self.data}), self.status_code


class NotFoundError(AppError):
    def __init__(self, resource: str, id_val: Any = None):
        msg = f"{resource}不存在" if id_val is None else f"{resource} (id={id_val}) 不存在"
        super().__init__(msg, status_code=404)


class ForbiddenError(AppError):
    def __init__(self, msg: str = "权限不足"):
        super().__init__(msg, status_code=403)


class UnauthorizedError(AppError):
    def __init__(self, msg: str = "请先登录"):
        super().__init__(msg, status_code=401)


class ValidationError(AppError):
    def __init__(self, msg: str):
        super().__init__(msg, status_code=400)


class ConflictError(AppError):
    def __init__(self, msg: str):
        super().__init__(msg, status_code=409)


class ServiceError(AppError):
    """服务层内部错误（不直接暴露给客户端）"""
    def __init__(self, msg: str, original: Optional[Exception] = None):
        super().__init__(f"服务内部错误: {msg}", status_code=500)
        self.original = original


def register_error_handlers(app):
    """向 Flask app 注册集中化异常处理"""
    @app.errorhandler(AppError)
    def handle_app_error(e: AppError):
        return e.to_response()

    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({"success": False, "msg": "接口不存在"}), 404

    @app.errorhandler(500)
    def handle_500(e):
        return jsonify({"success": False, "msg": "服务器内部错误"}), 500

    return app
