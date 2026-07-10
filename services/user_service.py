"""用户服务 — 注册、登录、画像分析"""
from datetime import datetime, timezone
from app import db
from repositories.data_access import UserRepository
from utils.errors import ValidationError, NotFoundError, ForbiddenError


class UserService:
    """用户管理服务"""

    @staticmethod
    def register(username: str, password: str):
        """注册新用户"""
        from app import PW_MIN_LEN

        if not username or not password:
            raise ValidationError("用户名或密码不能为空")
        if len(username) < 2 or len(username) > 30:
            raise ValidationError("用户名长度需在 2~30 个字符之间")
        if len(password) < PW_MIN_LEN:
            raise ValidationError(f"密码不能少于{PW_MIN_LEN}位")
        if UserRepository.get_by_username(username):
            raise ValidationError("该用户名已被占用")

        from app import User
        from werkzeug.security import generate_password_hash
        user = User(username=username, is_admin=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def authenticate(username: str, password: str):
        """验证用户登录"""
        if not username or not password:
            raise ValidationError("用户名或密码不能为空")

        user = UserRepository.get_by_username(username)
        if not user or not user.check_password(password):
            raise ValidationError("用户名或密码错误")
        return user

    @staticmethod
    def change_password(user, old_password: str, new_password: str):
        from app import PW_MIN_LEN
        if not user.check_password(old_password):
            raise ValidationError("原密码错误")
        if len(new_password) < PW_MIN_LEN:
            raise ValidationError(f"新密码不能少于{PW_MIN_LEN}位")
        user.set_password(new_password)
        db.session.commit()

    @staticmethod
    def update_tags(user, tags: str):
        user.persona_tags = tags if tags else None
        db.session.commit()

    @staticmethod
    def analyze_persona(user) -> dict:
        """生成用户画像"""
        from app import llm_client, LLM_MODEL, PERSONA_HISTORY_WINDOW
        from repositories.data_access import ChatRepository

        records = (ChatRepository.get_recent_history(user.id, 999999, limit=PERSONA_HISTORY_WINDOW)
                   if hasattr(ChatRepository, 'get_recent_history') else [])
        if not records:
            raise ValidationError("数据不足，无法生成画像")

        dialogue = []
        for r in reversed(records):
            if r.text:
                dialogue.append(f"[用户]: {r.text} (情绪: {r.emotion})")
            if r.reply:
                sender = "人工客服" if r.is_admin_reply else "AI助手"
                dialogue.append(f"[{sender}]: {r.reply}")

        prompt = ("你是专业的客户行为分析系统。根据以下对话记录生成用户画像JSON："
                  '{"tags": "3-5个特征标签，逗号分隔", "summary": "50字以内的用户诉求摘要"}')

        resp = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "\n".join(dialogue)}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=500
        )

        import json
        data = json.loads(resp.choices[0].message.content)
        user.persona_tags = str(data.get('tags', ''))
        user.persona_summary = data.get('summary', '')
        user.last_analyzed = datetime.now(timezone.utc)
        db.session.commit()
        return data

    @staticmethod
    def get_profile(user) -> dict:
        from repositories.data_access import OrderRepository
        orders = [{"id": o.id, "number": o.order_number, "item": o.item_name,
                   "status": o.status,
                   "arrival": o.estimated_arrival.strftime('%Y-%m-%d') if o.estimated_arrival else "待定",
                   "order_date": o.order_date.strftime('%Y-%m-%d') if o.order_date else ""}
                  for o in OrderRepository.get_by_user(user.id)]
        return {"username": user.username, "tags": user.get_tags() if user.persona_tags else [],
                "summary": user.persona_summary, "orders": orders}
