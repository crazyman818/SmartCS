"""数据库优化工具 — 对应 backend-patterns 的 Transaction + N+1 Prevention"""
from contextlib import contextmanager
from app import db


@contextmanager
def transaction():
    """事务上下文管理器 — 自动 commit/rollback"""
    try:
        yield
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def commit_or_rollback():
    """提交或回滚，返回是否成功"""
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def paginate(query, page: int = 1, per_page: int = 20) -> dict:
    """通用分页辅助"""
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }
