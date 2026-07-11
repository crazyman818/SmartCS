import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

_flask_socketio_async_mode = os.environ.get("SOCKETIO_ASYNC_MODE", "eventlet").strip()
if _flask_socketio_async_mode == "eventlet":
    import eventlet
    eventlet.monkey_patch()
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any, List
from functools import wraps
import json
import math
import traceback
import warnings
import importlib
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# 可选：RAG 向量检索（无网络/无依赖时会自动降级为关键词检索）
SentenceTransformer = None  # type: ignore

from flask import Flask, render_template, request, jsonify, redirect, url_for, abort, flash
from flask_login import (
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

from openai import OpenAI

# Flask-SocketIO 支持 - 必须在使用 gevent 之前配置 async_mode
# 尝试使用 threading 模式（最兼容），失败则回退
from flask_socketio import emit, join_room, leave_room
from smartcs.config import get_config
from smartcs.extensions import csrf, db, limiter, login_manager, socketio

import torch
import torch.nn.functional as F
from transformers import BertTokenizer, BertForSequenceClassification

# 尝试导入改进的模型（sys.path 已在文件头部配置）
try:
    from models.improved_bert_model import ImprovedBertForSequenceClassification
    IMPROVED_MODEL_AVAILABLE = True
except ImportError:
    IMPROVED_MODEL_AVAILABLE = False
    ImprovedBertForSequenceClassification = None

# ============================================================
# App / DB / Login config
# ============================================================
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    instance_path=str(BASE_DIR / "instance"),
)
app.config.from_object(get_config())

_secret_key = os.environ.get("SECRET_KEY")
_debug_mode = os.environ.get("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

if not _secret_key:
    if _debug_mode:
        _secret_key = "dev-insecure-default-do-not-use-in-prod"
        warnings.warn(
            "[WARN] SECRET_KEY 未通过环境变量设置，使用了不安全的开发默认值。",
            RuntimeWarning, stacklevel=1,
        )
    else:
        raise RuntimeError(
            "SECRET_KEY 必须设置！生产环境不允许使用默认密钥。"
        )
app.config["SECRET_KEY"] = _secret_key

# Session 安全配置
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("HTTPS", "").strip().lower() in {"1", "true", "yes", "on"}

# CSRF / rate limiting
app.config["WTF_CSRF_CHECK_DEFAULT"] = False
csrf.init_app(app)
limiter.init_app(app)

_db_uri = os.environ.get("DATABASE_URL", "sqlite:///site.db")
app.config["SQLALCHEMY_DATABASE_URI"] = _db_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 🔴【修复】SQLite 并发写入优化：WAL 模式 + busy timeout，避免 "database is locked"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"check_same_thread": False},
    "pool_pre_ping": True,
    # SQLite 特有的 pragma 在连接时设置
}

# 在 app context 创建后应用 pragma（通过事件监听）
import sqlalchemy
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """为 SQLite 连接启用 WAL 模式并设置 busy_timeout"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

# 延迟注册（db 实例创建后）
_set_pragma_registered = False

def _register_sqlite_pragma():
    global _set_pragma_registered
    if not _set_pragma_registered and "sqlite" in _db_uri.lower():
        import sqlalchemy as _sa
        from sqlalchemy import event
        event.listens_for(_sa.engine.Engine, "connect")(_set_sqlite_pragma)
        _set_pragma_registered = True


def _ensure_indexes():
    """确保数据库索引存在（对已有数据库增量创建）"""
    from sqlalchemy import text
    indexes = [
        'CREATE INDEX IF NOT EXISTS idx_chat_user_timestamp ON chat_record(user_id, timestamp)',
        'CREATE INDEX IF NOT EXISTS idx_chat_emotion ON chat_record(emotion)',
        'CREATE INDEX IF NOT EXISTS idx_chat_is_admin ON chat_record(is_admin_reply)',
        'CREATE INDEX IF NOT EXISTS idx_chat_feedback ON chat_record(feedback)',
        'CREATE INDEX IF NOT EXISTS idx_user_needs_intervention ON user(needs_intervention)',
        'CREATE INDEX IF NOT EXISTS idx_user_risk_level ON user(risk_level)',
        'CREATE INDEX IF NOT EXISTS idx_order_user_id ON orders(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_refund_user_id ON refund_requests(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_refund_status ON refund_requests(status)',
        'CREATE INDEX IF NOT EXISTS idx_refund_created ON refund_requests(created_at)',
        'CREATE INDEX IF NOT EXISTS idx_kb_enabled ON knowledge_qa(enabled)',
        'CREATE INDEX IF NOT EXISTS idx_intent_timestamp ON intent_stats(timestamp)',
    ]
    for sql in indexes:
        try:
            db.session.execute(text(sql))
        except Exception:
            pass
    db.session.commit()


# SocketIO configuration
app.config["SOCKETIO_MESSAGE_QUEUE"] = os.environ.get("SOCKETIO_MESSAGE_QUEUE", None)
app.config["SOCKETIO_CORS_ALLOWED_ORIGINS"] = os.environ.get(
    "SOCKETIO_CORS_ALLOWED_ORIGINS",
    os.environ.get("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5000,http://localhost:5000"),
)
app.config["SOCKETIO_ASYNC_MODE"] = _flask_socketio_async_mode

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"

socketio.init_app(
    app,
    cors_allowed_origins=app.config["SOCKETIO_CORS_ALLOWED_ORIGINS"],
    async_mode=_flask_socketio_async_mode,
    ping_timeout=60,
    ping_interval=25,
)

# Register centralized error handlers (backend-patterns)
from utils.errors import register_error_handlers, AppError, NotFoundError, ValidationError, ForbiddenError
register_error_handlers(app)


@app.after_request
def apply_security_headers(response):
    """Apply conservative browser security headers."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response
# 延迟导入 Service 和 Repository 层 (避免循环依赖)
# 在路由中通过 from services.xxx import XxxService 按需导入

# ============================================================
# LLM config (DeepSeek / OpenAI-compatible)
# ============================================================
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

if LLM_API_KEY:
    llm_client: Optional[OpenAI] = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
else:
    llm_client = None
    warnings.warn(
        "[WARN] LLM_API_KEY 未设置，LLM 调用将降级到兜底回复。请设置 LLM_API_KEY 环境变量以启用 AI 回复。",
        RuntimeWarning, stacklevel=1,
    )

SYSTEM_PROMPT_TEMPLATE = (
    "你是一个专业、耐心、同理心强的电商客服助手。"
    "你会根据用户情绪做出合适的安抚与解决方案建议。"
    "当前识别到的用户情绪是：{emotion}。"
    "要求：简洁（80字以内），先共情后给下一步行动建议。"
)

# ============================================================
# BERT emotion model config
# ============================================================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 与 models/train_bert.py 的 LABEL_MAP 保持一致：
# 0 neutral, 1 happy, 2 angry, 3 sad, 4 fear, 5 surprise
LABEL_MAP: Dict[int, str] = {
    0: "neutral",
    1: "happy",
    2: "angry",
    3: "sad",
    4: "fear",
    5: "surprise",
}

MODEL_PATH = os.path.join(os.getcwd(), "models", "my_finetuned_bert")

tokenizer: Optional[BertTokenizer] = None
emotion_model: Optional[BertForSequenceClassification] = None
use_improved_model: bool = False


def load_emotion_model() -> None:
    global tokenizer, emotion_model, use_improved_model
    try:
        tokenizer = BertTokenizer.from_pretrained(MODEL_PATH)

        # 读取模型信息文件（如果存在）
        model_info_path = os.path.join(MODEL_PATH, "model_info.json")
        model_type = 'original'
        pooling_strategy = 'cls'

        if os.path.exists(model_info_path):
            with open(model_info_path, 'r', encoding='utf-8') as f:
                model_info = json.load(f)
                model_type = model_info.get('model_type', 'original')
                pooling_strategy = model_info.get('pooling_strategy', 'cls')

        # 根据模型类型加载对应模型
        if model_type == 'improved' and IMPROVED_MODEL_AVAILABLE:
            print(f"  -> 加载改进模型 (Pooling: {pooling_strategy})")
            # 读取基础模型配置
            from transformers import AutoConfig
            config = AutoConfig.from_pretrained(MODEL_PATH)
            emotion_model = ImprovedBertForSequenceClassification.from_pretrained(MODEL_PATH)
            use_improved_model = True
        else:
            emotion_model = BertForSequenceClassification.from_pretrained(MODEL_PATH)
            use_improved_model = False

        emotion_model.to(device)
        emotion_model.eval()
        print(f"[OK] Emotion model loaded from: {MODEL_PATH} (type: {model_type})")
    except Exception as e:
        tokenizer = None
        emotion_model = None
        use_improved_model = False
        print(f"[WARN] Emotion model load failed: {e}")
        print("[WARN] Will fallback to keyword-based emotion detection.")


def predict_emotion(text: str) -> Tuple[str, float]:
    """
    预测文本情绪：优先用 BERT；失败则关键词兜底。
    返回：(emotion_label, confidence)
    """
    text = (text or "").strip()
    if not text:
        return "neutral", 0.0

    if emotion_model is not None and tokenizer is not None:
        try:
            inputs = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=128,
            ).to(device)

            with torch.no_grad():
                outputs = emotion_model(**inputs)
                # 适配改进模型的输出格式
                if use_improved_model and isinstance(outputs, dict):
                    logits = outputs['logits']
                else:
                    logits = outputs.logits
                probs = F.softmax(logits, dim=1)
                confidence, predicted_class = torch.max(probs, dim=1)

            label = LABEL_MAP.get(int(predicted_class.item()), "neutral")
            return label, float(confidence.item())
        except Exception as e:
            print(f"[WARN] predict_emotion failed, fallback. err={e}")

    # fallback (简单兜底)
    lower = text.lower()
    if any(k in text for k in ["气死", "滚", "投诉", "差评", "欺骗", "垃圾", "生气"]):
        return "angry", 0.40
    if any(k in text for k in ["害怕", "恐惧", "担心", "慌", "焦虑"]):
        return "fear", 0.40
    if any(k in text for k in ["难过", "伤心", "想哭", "崩溃", "失望"]):
        return "sad", 0.40
    if any(k in text for k in ["开心", "太好了", "满意", "喜欢", "谢谢"]):
        return "happy", 0.40
    if any(k in text for k in ["哇", "震惊", "竟然", "没想到"]):
        return "surprise", 0.40
    if any(k in lower for k in ["wtf", "angry", "mad"]):
        return "angry", 0.35
    return "neutral", 0.30


def generate_llm_reply(
    user_text: str,
    emotion: str,
    extra_system_info: str = "",
    history: Optional[List] = None,
) -> str:
    """
    LLM 生成回复：支持多轮对话上下文（history 为最近若干条 ChatRecord）。
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return "请告诉我具体问题，我来帮您处理。"

    if llm_client is None:
        return "AI 回复服务暂未配置，请联系管理员设置 LLM_API_KEY。"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(emotion=emotion)
    if extra_system_info:
        system_prompt += (
            f"\n\n【系统提供的业务数据】:\n{extra_system_info}\n"
            "请结合业务数据回答用户。如果用户想确认收货，请引导他们点击卡片上的按钮。"
        )

    # 构建多轮对话消息列表
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if history:
        for rec in history:
            if rec.text and rec.text.strip():
                messages.append({"role": "user", "content": rec.text.strip()})
            if rec.reply and rec.reply.strip() and not rec.is_admin_reply:
                messages.append({"role": "assistant", "content": rec.reply.strip()})
    messages.append({"role": "user", "content": user_text})

    try:
        resp = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=180,
        )
        return (resp.choices[0].message.content or "").strip() or "我在的，请继续说说具体情况。"
    except Exception as e:
        print(f"[WARN] LLM call failed: {e}")
        return "系统繁忙，我先记录问题。请提供订单号/截图，我会尽快帮您处理。"


def analyze_user_persona(user_id):
    """
    使用 DeepSeek 模型生成用户画像 (适配 Q&A 数据库结构)
    """
    if llm_client is None:
        return {"success": False, "msg": "AI 服务未配置（LLM_API_KEY 未设置）"}

    print(f"DeepSeek 正在分析用户 {user_id} ...")

    user = db.session.get(User, user_id)
    if not user:
        return {"success": False, "msg": "用户不存在"}

    records = ChatRecord.query.filter_by(user_id=user_id) \
        .order_by(ChatRecord.timestamp.desc()) \
        .limit(20).all()

    if not records:
        return {"success": False, "msg": "数据不足，无法生成画像"}

    dialogue_lines = []

    for r in reversed(records):
        if r.text:
            emotion_info = f"(检测情绪: {r.emotion})" if r.emotion else ""
            dialogue_lines.append(f"[用户]: {r.text} {emotion_info}")

        if r.reply:
            sender_name = "人工客服" if r.is_admin_reply else "AI助手"
            dialogue_lines.append(f"[{sender_name}]: {r.reply}")

    chat_text = "\n".join(dialogue_lines)

    system_instruction = """
    你是一个专业的客户行为分析系统。
    请根据用户的聊天记录生成画像。

    请输出严格的 JSON 格式，包含以下字段：
    1. "tags": (字符串) 3-5个简短的特征标签，用逗号分隔。
    2. "summary": (字符串) 50字以内的用户诉求摘要和接待建议。
    """

    try:
        response = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"对话记录如下：\n{chat_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=500
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        # 5. 保存结果到数据库
        tags_raw = data.get('tags', '')
        if isinstance(tags_raw, list):
            user.persona_tags = ",".join(tags_raw)
        else:
            user.persona_tags = str(tags_raw)

        user.persona_summary = data.get('summary', '')
        user.last_analyzed = datetime.now(timezone.utc)

        db.session.commit()
        return {"success": True, "data": data}

    except Exception as e:
        print(f"DeepSeek 调用失败: {e}")
        return {"success": False, "msg": str(e)}


# ============================================================
# Database models
# ============================================================
class User(UserMixin, db.Model):
    __table_args__ = (
        db.Index('idx_user_needs_intervention', 'needs_intervention'),
        db.Index('idx_user_risk_level', 'risk_level'),
    )
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, index=True)

    persona_tags = db.Column(db.String(255), default="新用户")  # 例如: "急躁, 价格敏感, 需安抚"
    persona_summary = db.Column(db.Text, default="暂无详细画像")  # 例如: "用户经常询问退款问题，对服务态度要求较高..."
    last_analyzed = db.Column(db.DateTime)  # 上次生成画像的时间

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_tags(self):
        if not self.persona_tags:
            return []
        return self.persona_tags.split(',')

    # crisis intervention flags
    risk_counter = db.Column(db.Integer, default=0)  # 连续负面情绪计数
    needs_intervention = db.Column(db.Boolean, default=False)
    risk_level = db.Column(db.String(20), default='normal')  # normal / yellow / red

    # 当进入干预模式后：AI 只发一次提醒，然后"保持沉默"，直到管理员介入（发人工回复）
    intervention_notified = db.Column(db.Boolean, default=False)


# [新增] 订单模型
class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = (db.Index('idx_order_user_id', 'user_id'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    order_number = db.Column(db.String(50), unique=True, nullable=False)  # 订单号
    item_name = db.Column(db.String(100), nullable=False)  # 商品名
    status = db.Column(db.String(20), default="运输中")  # 状态
    order_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    estimated_arrival = db.Column(db.DateTime)  # 预计到货

    # 反向关联：user.orders 可获取列表
    user = db.relationship('User', backref=db.backref('orders', lazy=True))


class ChatRecord(db.Model):
    __table_args__ = (
        db.Index('idx_chat_user_timestamp', 'user_id', 'timestamp'),
        db.Index('idx_chat_emotion', 'emotion'),
        db.Index('idx_chat_is_admin', 'is_admin_reply'),
        db.Index('idx_chat_feedback', 'feedback'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    # 用户输入与系统回复
    text = db.Column(db.Text, default="")
    reply = db.Column(db.Text, default="")

    emotion = db.Column(db.String(50), default="neutral")
    confidence = db.Column(db.Float, default=0.0)

    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # admin reply flag
    is_admin_reply = db.Column(db.Boolean, default=False)

    # feedback: 0 none, 1 like, -1 dislike (点赞/踩)
    feedback = db.Column(db.Integer, default=0)

    # rating: 1-5 star rating, independent from feedback; 0 means not rated
    rating = db.Column(db.Integer, default=0)

    # relationship to User
    user = db.relationship('User', backref=db.backref('chat_records', lazy=True))


class QuickReply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(400), nullable=False)


class RefundRequest(db.Model):
    """退款工单：用户发起，管理员审批"""
    __tablename__ = 'refund_requests'
    __table_args__ = (
        db.Index('idx_refund_user_id', 'user_id'),
        db.Index('idx_refund_status', 'status'),
        db.Index('idx_refund_created', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)

    reason = db.Column(db.Text, nullable=False)
    # 待审核 / 已批准 / 已拒绝
    status = db.Column(db.String(20), default='待审核')
    admin_note = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('refund_requests', lazy=True))
    order = db.relationship('Order', backref=db.backref('refund_requests', lazy=True))


# ============================================================
# [新增] Knowledge Base (RAG) models
# ============================================================
class KnowledgeQA(db.Model):
    """知识库：结构化 Q&A，用于检索增强（RAG）"""
    __tablename__ = "knowledge_qa"
    __table_args__ = (db.Index('idx_kb_enabled', 'enabled'),)

    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default="")  # faq / general / ...
    tags = db.Column(db.String(255), default="")
    enabled = db.Column(db.Boolean, default=True)

    # 向量（JSON 序列化的 float list），用于相似度检索；为空则走关键词检索
    embedding = db.Column(db.Text, default="")

    use_count = db.Column(db.Integer, default=0)  # 调用次数统计

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None


# ============================================================
# [新增] Knowledge Base (RAG) utilities
# ============================================================
_kb_embedder = None


def _get_kb_embedder():
    """
    返回 SentenceTransformer 实例（如果可用）。初始化可能会下载模型，失败则返回 None 并自动降级。
    """
    global _kb_embedder
    if _kb_embedder is not None:
        return _kb_embedder

    global SentenceTransformer
    if SentenceTransformer is None:
        try:
            SentenceTransformer = importlib.import_module("sentence_transformers").SentenceTransformer  # type: ignore
        except Exception:
            return None

    model_name = os.environ.get("KB_EMBED_MODEL") or "paraphrase-multilingual-MiniLM-L12-v2"
    try:
        # 设置较短的超时时间避免加载失败时长时间卡住
        import socket
        socket.setdefaulttimeout(10)
        _kb_embedder = SentenceTransformer(model_name)
        return _kb_embedder
    except Exception as e:
        warnings.warn(f"[WARN] KB embed model load failed, fallback to keyword search. err={e}", RuntimeWarning)
        _kb_embedder = None
        return None
    finally:
        import socket
        socket.setdefaulttimeout(None)  # 恢复默认


def _embed_text(text: str) -> Optional[List[float]]:
    text = (text or "").strip()
    if not text:
        return None
    embedder = _get_kb_embedder()
    if embedder is None:
        return None
    try:
        vec = embedder.encode([text], normalize_embeddings=True)[0]
        return [float(x) for x in vec]
    except Exception as e:
        warnings.warn(f"[WARN] KB embed failed, fallback. err={e}", RuntimeWarning)
        return None


def _cosine(a: List[float], b: List[float]) -> float:
    # 向量已 normalize_embeddings=True，理论上点积即余弦；这里仍做安全处理
    if not a or not b or len(a) != len(b):
        return -1.0
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    if math.isnan(s):
        return -1.0
    return float(s)


def kb_upsert_embedding_for_qa(row: KnowledgeQA) -> None:
    """
    为 KnowledgeQA 计算并写入 embedding。失败不抛异常（自动降级）。
    """
    text = f"Q: {row.question}\nA: {row.answer}"
    vec = _embed_text(text)
    if vec is None:
        row.embedding = ""
        return
    row.embedding = json.dumps(vec, ensure_ascii=False)


def kb_search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    检索知识库，返回 [{id, question, answer, tags, score}]。
    - 优先向量检索（若 embedding 可用）
    - 否则使用简单关键词匹配（contains/重叠）
    """
    query = (query or "").strip()
    if not query:
        return []

    q_vec = _embed_text(query)
    rows: List[KnowledgeQA] = (
        KnowledgeQA.query.filter_by(enabled=True)
        .order_by(KnowledgeQA.updated_at.desc())
        .limit(500)
        .all()
    )

    scored: List[Dict[str, Any]] = []
    if q_vec is not None:
        for r in rows:
            if not r.embedding:
                continue
            try:
                v = json.loads(r.embedding)
                if isinstance(v, list):
                    score = _cosine(q_vec, [float(x) for x in v])
                else:
                    continue
            except Exception:
                continue
            scored.append(
                {
                    "id": r.id,
                    "question": r.question,
                    "answer": r.answer,
                    "tags": r.tags or "",
                    "score": float(score),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: max(1, int(top_k))]

    # 关键词检索降级（适配离线/无模型场景）
    q_lower = query.lower()
    for r in rows:
        blob = f"{r.question}\n{r.answer}\n{r.tags or ''}"
        blob_lower = blob.lower()
        if q_lower in blob_lower:
            score = 1.0
        else:
            hits = 0
            for ch in set(q_lower):
                if ch.strip() and ch in blob_lower:
                    hits += 1
            score = hits / max(1, len(set(q_lower)))
        scored.append(
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "tags": r.tags or "",
                "score": float(score),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(1, int(top_k))]


def kb_build_context(query: str, top_k: int = 3) -> str:
    hits = kb_search(query, top_k=top_k)
    if not hits:
        return ""
    lines = ["【知识库检索结果】（优先参考以下已审核内容作答，避免编造）"]
    for i, h in enumerate(hits, start=1):
        q = (h.get("question") or "").strip()
        a = (h.get("answer") or "").strip()
        t = (h.get("tags") or "").strip()
        lines.append(f"{i}. Q: {q}")
        lines.append(f"   A: {a}")
        if t:
            lines.append(f"   tags: {t}")
    return "\n".join(lines)


# ============================================================
# 通用工具：装饰器、常量、序列化
# ============================================================
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"success": False, "msg": "forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


# 状态常量
ORDER_SHIPPED, ORDER_IN_TRANSIT = ("已发货", "运输中")
ORDER_DELIVERED, ORDER_REFUNDED = ("已送达", "已退款")
REFUND_PENDING, REFUND_APPROVED, REFUND_REJECTED = ("待审核", "已批准", "已拒绝")

# LLM 参数
LLM_MAX_INPUT, LLM_TEMP, LLM_MAX_TOKENS = (2000, 0.7, 180)
CHAT_HISTORY_WINDOW = 8
KB_TOP_K, KB_SCAN_LIMIT = (3, 500)

# 危机阈值
CRISIS_CONSECUTIVE = 3
CRISIS_CONFIDENCE = 0.7

# 退款预警阈值
REFUND_YELLOW_COUNT, REFUND_YELLOW_RATE = (5, 30.0)
REFUND_RED_COUNT, REFUND_RED_RATE = (10, 50.0)

# 验证参数
PW_MIN_LEN = 8
CHAT_MAX_LEN = 2000


def safe_emit(event, data, room):
    try:
        socketio.emit(event, data, room=room)
    except Exception:
        logger.warning("WS emit failed: %s room=%s", event, room)


def chat_record_to_dict(r):
    return {
        "id": r.id, "text": r.text, "reply": r.reply,
        "emotion": r.emotion, "confidence": r.confidence,
        "timestamp": r.timestamp.isoformat(),
        "is_admin_reply": bool(r.is_admin_reply),
        "feedback": int(r.feedback or 0), "rating": int(r.rating or 0),
    }


def daily_trend(model, date_field, days=7):
    today = datetime.now(timezone.utc).date()
    return [{"date": (today - timedelta(days=d)).strftime("%m-%d"),
             "count": model.query.filter(
                 date_field >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(days=d),
                 date_field < datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(days=d-1)
             ).count()} for d in range(days - 1, -1, -1)]


# ============================================================
# [增强] 智能意图识别模块（12+意图类别）
# 对应论文第3章：意图识别与路由
# ============================================================
# 意图类别常量
INTENT_ORDER_QUERY = "order_query"          # 订单查询
INTENT_LOGISTICS = "logistics"              # 物流/发货
INTENT_ORDER_RECEIVED = "order_received"     # 确认收货/到货
INTENT_REFUND = "refund"                    # 退款
INTENT_RETURN_EXCHANGE = "return_exchange"  # 退货/换货
INTENT_COMPLAINT = "complaint"              # 投诉/差评
INTENT_TRANSFER_HUMAN = "transfer_human"    # 转人工
INTENT_PAYMENT = "payment"                  # 支付问题
INTENT_INVOICE = "invoice"                  # 发票
INTENT_ACCOUNT = "account"                  # 账号/密码/注销
INTENT_GREETING = "greeting"                # 问候/感谢
INTENT_CHITCHAT = "chitchat"               # 闲聊/其他
INTENT_PRODUCT_QUALITY = "product_quality"  # 商品质量
INTENT_PRICE = "price"                      # 价格/优惠

# 意图分组（路由用）
INTENT_ORDER_GROUP = {INTENT_ORDER_QUERY, INTENT_LOGISTICS, INTENT_ORDER_RECEIVED}
INTENT_REFUND_GROUP = {INTENT_REFUND, INTENT_RETURN_EXCHANGE}
INTENT_COMPLAINT_GROUP = {INTENT_COMPLAINT, INTENT_PRODUCT_QUALITY}
INTENT_TRANSFER_GROUP = {INTENT_TRANSFER_HUMAN}
INTENT_PAYMENT_GROUP = {INTENT_PAYMENT, INTENT_INVOICE, INTENT_PRICE}
INTENT_ACCOUNT_GROUP = {INTENT_ACCOUNT}
INTENT_GREETING_GROUP = {INTENT_GREETING, INTENT_CHITCHAT}

# 关键词-意图映射表（4层架构：输入层→编码层→分类层→响应层）
INTENT_KEYWORD_MAP: List[Tuple[str, str]] = [
    # 订单查询
    ("订单", INTENT_ORDER_QUERY), ("查件", INTENT_ORDER_QUERY), ("我的单", INTENT_ORDER_QUERY),
    ("买了什么", INTENT_ORDER_QUERY), ("下单", INTENT_ORDER_QUERY), ("购买记录", INTENT_ORDER_QUERY),
    # 物流
    ("物流", INTENT_LOGISTICS), ("发货", INTENT_LOGISTICS), ("到哪", INTENT_LOGISTICS),
    ("快递", INTENT_LOGISTICS), ("送到", INTENT_LOGISTICS), ("还没到", INTENT_LOGISTICS),
    ("运输", INTENT_LOGISTICS), ("配送", INTENT_LOGISTICS), ("派送", INTENT_LOGISTICS),
    # 确认收货
    ("到货", INTENT_ORDER_RECEIVED), ("收到", INTENT_ORDER_RECEIVED), ("收货", INTENT_ORDER_RECEIVED),
    ("确认收货", INTENT_ORDER_RECEIVED), ("已收到", INTENT_ORDER_RECEIVED),
    # 退款
    ("退款", INTENT_REFUND), ("退钱", INTENT_REFUND), ("退费", INTENT_REFUND),
    # 退货/换货
    ("退货", INTENT_RETURN_EXCHANGE), ("换货", INTENT_RETURN_EXCHANGE), ("退换", INTENT_RETURN_EXCHANGE),
    ("退回去", INTENT_RETURN_EXCHANGE), ("换个", INTENT_RETURN_EXCHANGE),
    # 投诉
    ("投诉", INTENT_COMPLAINT), ("差评", INTENT_COMPLAINT), ("举报", INTENT_COMPLAINT),
    ("曝光", INTENT_COMPLAINT), ("欺骗", INTENT_COMPLAINT), ("垃圾", INTENT_COMPLAINT),
    # 转人工
    ("转人工", INTENT_TRANSFER_HUMAN), ("人工客服", INTENT_TRANSFER_HUMAN), ("人工服务", INTENT_TRANSFER_HUMAN),
    ("真人", INTENT_TRANSFER_HUMAN), ("不是机器人", INTENT_TRANSFER_HUMAN), ("找人工", INTENT_TRANSFER_HUMAN),
    # 支付
    ("支付", INTENT_PAYMENT), ("付款", INTENT_PAYMENT), ("扣款", INTENT_PAYMENT),
    ("支付失败", INTENT_PAYMENT), ("没付", INTENT_PAYMENT),
    # 发票
    ("发票", INTENT_INVOICE), ("开票", INTENT_INVOICE), ("报销", INTENT_INVOICE),
    # 账号
    ("密码", INTENT_ACCOUNT), ("账号", INTENT_ACCOUNT), ("注销", INTENT_ACCOUNT),
    ("登录", INTENT_ACCOUNT), ("注册", INTENT_ACCOUNT), ("修改密码", INTENT_ACCOUNT),
    # 问候
    ("你好", INTENT_GREETING), ("嗨", INTENT_GREETING), ("在吗", INTENT_GREETING),
    ("谢谢", INTENT_GREETING), ("感谢", INTENT_GREETING), ("再见", INTENT_GREETING),
    # 商品质量
    ("质量", INTENT_PRODUCT_QUALITY), ("坏了", INTENT_PRODUCT_QUALITY), ("破损", INTENT_PRODUCT_QUALITY),
    ("有问题", INTENT_PRODUCT_QUALITY), ("瑕疵", INTENT_PRODUCT_QUALITY),
    # 价格
    ("价格", INTENT_PRICE), ("优惠", INTENT_PRICE), ("便宜", INTENT_PRICE),
    ("贵了", INTENT_PRICE), ("折扣", INTENT_PRICE), ("降价", INTENT_PRICE),
]


from smartcs.services.intent_service import IntentRule, IntentService

_intent_service = IntentService(
    [IntentRule(intent=intent, keywords=(keyword,)) for keyword, intent in INTENT_KEYWORD_MAP],
    default_intent=INTENT_CHITCHAT,
)


def classify_intent(text: str) -> str:
    """Classify a user message into a SmartCS intent label."""
    try:
        return _intent_service.classify(text)
    except Exception as e:
        print(f"[WARN] classify_intent failed: {e}")
        return INTENT_CHITCHAT

class IntentStat(db.Model):
    """意图统计模型 - 对应论文第4章数据分析模块"""
    __tablename__ = "intent_stats"
    __table_args__ = (db.Index('idx_intent_timestamp', 'timestamp'),)
    id = db.Column(db.Integer, primary_key=True)
    intent = db.Column(db.String(50), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # relationship to User
    user = db.relationship('User', backref=db.backref('intent_stats', lazy=True))


def log_intent_stat(intent: str, user_id: int) -> None:
    """记录意图统计（写入数据库）"""
    try:
        stat = IntentStat(intent=intent, user_id=user_id)
        db.session.add(stat)
        # 不在这里 commit，由外层 api_chat 统一提交
    except Exception as e:
        print(f"[WARN] log_intent_stat failed: {e}")


# ============================================================
# Crisis intervention logic
# ============================================================
NEGATIVE_EMOTIONS = {"sad", "fear", "angry"}

# 极端关键词列表（红色预警触发）
EXTREME_KEYWORDS = [
    "不想活", "自杀", "死了算了", "活不下去", "不想活了",
    "报警", "投诉到媒体", "找记者", "曝光你们",
    "法院", "起诉", "律师", "12315", "315",
    "人身安全", "威胁", "要命",
]

YELLOW_CARE_MESSAGE = (
    "我注意到您似乎有些情绪波动，我非常理解您的感受。"
    "请放心，我会尽我所能帮助您解决问题。"
    "如果需要，我也可以为您转接人工客服，提供更贴心的帮助。"
)

RED_ALERT_MESSAGE = (
    "我们非常重视您的情况。系统已暂停自动回复，"
    "人工客服正在紧急介入中，请稍等片刻。"
    "如遇紧急情况，您也可以拨打心理援助热线：400-161-9995。"
)


def get_recent_emotions(user_id: int, limit: int = 5) -> List[Tuple[str, float]]:
    """获取用户最近 N 条消息的情感分数"""
    records = (
        ChatRecord.query.filter_by(user_id=user_id)
        .filter(ChatRecord.text != "", ChatRecord.emotion != "")
        .order_by(ChatRecord.id.desc())
        .limit(limit)
        .all()
    )
    if not records:
        return []
    records = list(records)
    records.reverse()
    return [(r.emotion, r.confidence) for r in records]


def check_extreme_keywords(text: str) -> bool:
    """检查文本是否包含极端关键词"""
    for kw in EXTREME_KEYWORDS:
        if kw in text:
            return True
    return False


def update_risk_state_by_emotion(user: User, emotion: str, user_text: str = "") -> None:
    """
    扩展危机检测：
    - 黄色预警：连续 3+ 条负面情绪且负面情感平均分 > 0.7 → 发送关怀 + 通知管理员
    - 红色预警：极端关键词 → 立即转人工 + 心理热线
    - 情绪好转则 risk_counter 清零（但如果已经 needs_intervention，不自动解除）
    """
    # === 红色预警检测：极端关键词 ===
    if user_text and check_extreme_keywords(user_text):
        user.risk_level = 'red'
        user.needs_intervention = True
        user.intervention_notified = False
        # WebSocket 推送红色预警
        try:
            socketio.emit('crisis_alert', {
                'user_id': user.id,
                'username': user.username,
                'risk_level': 'red',
                'message': f'🔴 红色预警：用户 {user.username} 触发极端关键词，需要立即人工介入！'
            }, room='admin_room')
        except Exception as ws_err:
            print(f"[WARN] WebSocket 推送失败: {ws_err}")
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

    # === 黄色预警：连续 3+ 条负面情绪且平均分 > 0.7 ===
    if user.risk_counter >= 3:
        recent = get_recent_emotions(user.id, limit=5)
        # 取最近 3 条（按实际计数的最后 3 条）
        last_negatives = [(e, c) for e, c in recent if e in NEGATIVE_EMOTIONS][-3:]
        if len(last_negatives) >= 3:
            avg_conf = sum(c for _, c in last_negatives) / len(last_negatives)
            if avg_conf > 0.7:
                user.risk_level = 'yellow'

        user.needs_intervention = True
        user.intervention_notified = False
        risk_level = user.risk_level or 'normal'

        try:
            socketio.emit('crisis_alert', {
                'user_id': user.id,
                'username': user.username,
                'risk_counter': user.risk_counter,
                'risk_level': risk_level,
                'emotion': emotion,
                'message': f'{"🟡" if risk_level == "yellow" else "🔴"} 用户 {user.username} ({risk_level}预警)，需要人工介入'
            }, room='admin_room')

            socketio.emit('dashboard_update', {
                'type': 'crisis_intervention',
                'user_id': user.id,
                'username': user.username,
                'risk_level': risk_level,
                'needs_intervention': True
            }, room='admin_room')
        except Exception as ws_err:
            print(f"[WARN] WebSocket 推送失败: {ws_err}")


def update_risk_state_by_feedback(user: User) -> None:
    """
    规则：连续两次“踩” => needs_intervention = True
    注意：这里“连续两次”指最近两条 *AI回复* 的 feedback 都是 -1。
    """
    if user.needs_intervention:
        return

    recent_ai = (
        ChatRecord.query.filter_by(user_id=user.id)
        .filter(ChatRecord.reply != "")
        .filter(ChatRecord.is_admin_reply.is_(False))
        .order_by(ChatRecord.id.desc())
        .limit(2)
        .all()
    )

    if len(recent_ai) >= 2 and all(r.feedback == -1 for r in recent_ai):
        user.needs_intervention = True
        user.intervention_notified = False


def admin_has_intervened(user_id: int) -> bool:
    """
    管理员是否已经对该用户发过人工回复（用于解除“沉默锁”）
    这里定义：只要出现一条 is_admin_reply=True 的记录，就算介入过。
    """
    return (
            db.session.query(ChatRecord.id)
            .filter_by(user_id=user_id, is_admin_reply=True)
            .limit(1)
            .first()
            is not None
    )


# Service / Repository 层导入（在 app/db 初始化之后，无循环依赖）
from services.chat_service import ChatService
from services.crisis_service import CrisisService
from services.user_service import UserService
from repositories.data_access import (ChatRepository, UserRepository, OrderRepository,
                                       QuickReplyRepository, KnowledgeQARepository,
                                       RefundRepository, IntentStatRepository)

# ============================================================
# Routes: auth pages
# ============================================================
@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("chat_page"))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    # 1. 如果用户已经登录，直接跳过
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("chat_page"))

    # 2. 处理 POST 请求 (点击登录按钮)
    if request.method == "POST":
        # 🔴【修复】支持 JSON 格式登录请求（前端 fetch/AJAX 调用）
        if request.is_json:
            data = request.get_json(force=True, silent=True) or {}
            username = (data.get("username") or "").strip()
            password = data.get("password") or ""
        else:
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            # 🔴【修复】JSON 请求返回 JSON 响应，而非重定向
            if request.is_json:
                return jsonify({"status": "success", "msg": "登录成功", "is_admin": user.is_admin}), 200
            if user.is_admin:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("chat_page"))
        else:
            # 🔴【修复】JSON 请求返回 JSON 错误消息
            if request.is_json:
                return jsonify({"status": "error", "msg": "用户名或密码错误"}), 401
            # 🔴【核心修改】使用 flash 发送错误消息
            flash("用户名或密码错误", "error")

            # 失败后重定向回 login 页面（刷新页面），以便显示 flash 消息
            return redirect(url_for("login"))

    # 3. 处理 GET 请求 (打开页面)
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ============================================================
# Routes: user pages
# ============================================================
@app.route("/chat")
@login_required
def chat_page():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    return render_template("chat.html")


# ============================================================
# API: chat (MODIFIED)
# ============================================================
@app.route("/api/chat", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def api_chat():
    if current_user.is_admin:
        return jsonify({"status": "forbidden", "message": "admin cannot use user chat api"}), 403

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or payload.get("message") or payload.get("input") or "").strip()
    if not text:
        return jsonify({"status": "empty"}), 400
    if len(text) > CHAT_MAX_LEN:
        return jsonify({"status": "error", "msg": f"消息过长，最多{CHAT_MAX_LEN}字"}), 400

    emotion, conf = predict_emotion(text)

    # 先写入用户消息记录（text）
    user_record = ChatRecord(
        user_id=current_user.id,
        text=text,
        reply="",
        emotion=emotion,
        confidence=conf,
        is_admin_reply=False,
    )
    db.session.add(user_record)

    # 更新风险状态（连续负面情绪 + 极端关键词检测）
    update_risk_state_by_emotion(current_user, emotion, user_text=text)

    # ================= [增强] 智能意图识别（12+类别）=================
    intent = classify_intent(text)
    # 记录意图统计
    log_intent_stat(intent, current_user.id)

    extra_system_info_parts: List[str] = []
    orders_data_for_frontend = []

    # 根据意图类别路由到对应处理逻辑
    if intent in INTENT_ORDER_GROUP:  # 订单/物流/发货/查询/到货
        user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.order_date.desc()).all()
        if user_orders:
            info_list = []
            for o in user_orders:
                arrival_str = o.estimated_arrival.strftime('%Y-%m-%d') if o.estimated_arrival else "待定"
                info_list.append(f"单号:{o.order_number}, 商品:{o.item_name}, 状态:{o.status}, 预计:{arrival_str}")
                orders_data_for_frontend.append({
                    "id": o.id,
                    "number": o.order_number,
                    "item": o.item_name,
                    "status": o.status,
                    "arrival": o.estimated_arrival.strftime('%m-%d') if o.estimated_arrival else "待定"
                })
            extra_system_info_parts.append("【用户订单信息】\n" + "\n".join(info_list))
        else:
            extra_system_info_parts.append("【用户订单信息】\n用户当前没有任何订单记录。")

    elif intent in INTENT_REFUND_GROUP:  # 退款/退货/退换
        extra_system_info_parts.append(
            "【退款引导】用户询问退款相关事宜。请在回复中引导用户前往【个人中心】→【退款申请】提交退款工单。"
            "如已提交，告知用户可在【个人中心】→【退款列表】查看进度。审批通过后1-3个工作日原路退回。"
        )
    elif intent in INTENT_COMPLAINT_GROUP:  # 投诉/差评/举报
        extra_system_info_parts.append(
            "【投诉处理】用户表达强烈不满或投诉意图。请优先安抚情绪，表示歉意，"
            "并引导用户提供具体问题描述与订单号。告知将转交专人处理。"
        )
        # 自动标记为需干预
        if not current_user.needs_intervention:
            current_user.needs_intervention = True
            current_user.intervention_notified = False
    elif intent in INTENT_TRANSFER_GROUP:  # 转人工
        extra_system_info_parts.append(
            "【转人工请求】用户明确要求人工客服介入。请回复告知用户已记录请求，客服将尽快联系。"
        )
        if not current_user.needs_intervention:
            current_user.needs_intervention = True
            current_user.intervention_notified = False
    elif intent in INTENT_PAYMENT_GROUP:  # 支付/价格/发票
        extra_system_info_parts.append(
            "【支付/发票】用户询问支付或发票相关问题。请在知识库中查询发票开具流程，"
            "或引导用户提供订单号以便核实支付状态。"
        )
    elif intent in INTENT_ACCOUNT_GROUP:  # 账号/密码/注销
        extra_system_info_parts.append(
            "【账号管理】用户询问账号相关操作。密码修改可在【个人中心】操作，其他问题引导用户提供更多信息。"
        )
    elif intent in INTENT_GREETING_GROUP:  # 问候/感谢/闲聊
        extra_system_info_parts.append("【问候】用户在进行寒暄或表达感谢。请友好回应并询问是否需要帮助。")
    # =======================================================

    # ================= [新增] 知识库 RAG 检索 =================
    kb_ctx = kb_build_context(text, top_k=3)
    if kb_ctx:
        extra_system_info_parts.append(kb_ctx)
    # =======================================================

    extra_system_info = "\n\n".join([p for p in extra_system_info_parts if p.strip()])

    # 获取近期对话历史，用于多轮上下文（最近 8 条，约 4 轮对话）
    recent_history = (
        ChatRecord.query
        .filter_by(user_id=current_user.id)
        .filter(ChatRecord.id < user_record.id)
        .order_by(ChatRecord.id.desc())
        .limit(8)
        .all()
    )
    recent_history.reverse()

    # 生成回复逻辑（含：干预模式 AI 沉默）
    reply_text = ""
    should_speak = True

    if current_user.needs_intervention:
        intervened = admin_has_intervened(current_user.id)
        if not intervened:
            if not current_user.intervention_notified:
                reply_text = "（⚠️ 检测到您情绪波动较大，已为您转接人工客服，请稍候。您也可以留下订单号与问题要点。）"
                current_user.intervention_notified = True
            else:
                reply_text = ""  # 保持沉默
                should_speak = False
        else:
            try:
                reply_text = generate_llm_reply(text, emotion, extra_system_info, recent_history)
            except Exception as e:
                print(f"[ERROR] generate_llm_reply failed: {e}")
                reply_text = "系统繁忙，请稍后重试。如需帮助请转人工客服。"
    else:
        try:
            reply_text = generate_llm_reply(text, emotion, extra_system_info, recent_history)
        except Exception as e:
            print(f"[ERROR] generate_llm_reply failed: {e}")
            reply_text = "系统繁忙，请稍后重试。如需帮助请转人工客服。"

    # 写入回复记录（reply）
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
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] api_chat db commit failed: {e}")
        return jsonify({"status": "error", "message": "数据库写入失败，请稍后重试"}), 500

    # ========== WebSocket 推送：通知用户有新消息 ==========
    # 推送 AI 回复给用户房间
    socketio.emit('new_message', {
        'id': reply_record.id,
        'reply': reply_text,
        'emotion': emotion,
        'confidence': conf,
        'timestamp': reply_record.timestamp.isoformat(),
        'is_admin_reply': False,
        'feedback': 0,
        'intervention': bool(current_user.needs_intervention),
        'should_speak': bool(should_speak and bool(reply_text)),
    }, room=f'user_{current_user.id}')

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
            "orders_data": orders_data_for_frontend  # [新增] 返回订单数组给前端
        }
    )


# ============================================================
# [新增] API: Confirm Order
# ============================================================
@app.route('/api/order/confirm', methods=['POST'])
@login_required
def api_confirm_order():
    """ 用户点击“确认收货”时调用 """
    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id')
    if not order_id:
        return jsonify({'status': 'error', 'msg': '缺少 order_id'}), 400

    # 确保订单属于当前用户
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()

    if not order:
        return jsonify({'status': 'error', 'msg': '订单不存在'}), 404

    # 校验订单状态：已送达/已退款的订单无需重复确认
    if order.status in ('已送达', '已退款'):
        return jsonify({'status': 'error', 'msg': f'订单当前状态为"{order.status}"，无需重复确认收货'}), 400

    order.status = "已送达"
    db.session.commit()

    return jsonify({
        'status': 'success',
        'msg': f'订单 {order.order_number} 已确认收货',
        'new_status': '已送达'
    })


# ============================================================
# API: user polling get_messages
# ============================================================
@app.route("/api/get_messages", methods=["GET"])
@login_required
def api_get_messages():
    if current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    last_id = request.args.get("last_id", default=0, type=int)
    msgs = ChatService.get_messages_for_user(current_user.id, last_id)

    return jsonify({"status": "success", "messages": msgs, "intervention": bool(current_user.needs_intervention)})


# ============================================================
# API: feedback
# ============================================================
@app.route("/api/feedback", methods=["POST"])
@login_required
def api_feedback():
    if current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    record_id = payload.get("record_id")
    action = payload.get("action")  # "like" / "dislike"

    if not record_id or action not in ("like", "dislike"):
        return jsonify({"status": "bad_request"}), 400

    record = db.session.get(ChatRecord, int(record_id))
    if record is None or record.user_id != current_user.id:
        return jsonify({"status": "not_found"}), 404

    # 只能对 AI 回复记录做反馈（reply 非空且非管理员）
    if not record.reply or record.is_admin_reply:
        return jsonify({"status": "not_allowed"}), 400

    record.feedback = 1 if action == "like" else -1
    # rating 字段独立存储，不受 feedback 影响
    db.session.add(record)
    db.session.commit()

    # 更新干预：连续两次 dislike 触发（commit 之后才能看到最新的 feedback）
    update_risk_state_by_feedback(current_user)
    db.session.commit()

    return jsonify({"status": "success", "intervention": bool(current_user.needs_intervention)})


# ============================================================
# Admin pages
# ============================================================
@app.route("/admin")
@login_required
def admin_dashboard():
    # 1. 权限检查
    if not current_user.is_admin:
        return redirect(url_for("chat_page"))

    # 2. 原有的逻辑：获取危机干预队列 (按风险计数倒序)
    flagged_users = User.query.filter_by(needs_intervention=True, is_admin=False).order_by(
        User.risk_counter.desc()).all()

    #    这里按 ID 倒序排列，方便看到最新注册的用户
    all_users = User.query.filter_by(is_admin=False).order_by(User.id.desc()).all()

    # 4. 渲染模板时，把 all_users 也传进去
    return render_template("admin.html", flagged_users=flagged_users, all_users=all_users)


@app.route("/admin/chat/<int:user_id>")
@login_required
def admin_chat_page(user_id: int):
    if not current_user.is_admin:
        return redirect(url_for("chat_page"))

    target_user = db.session.get(User, user_id)
    if target_user is None:
        abort(404)

    history = ChatRecord.query.filter_by(user_id=user_id).order_by(ChatRecord.id.asc()).all()
    quick_replies = QuickReply.query.order_by(QuickReply.id.desc()).all()
    return render_template(
        "admin_chat.html",
        target_user=target_user,
        history=history,
        quick_replies=quick_replies,
    )


@app.route("/admin/kb")
@login_required
def admin_kb_page():
    if not current_user.is_admin:
        return redirect(url_for("chat_page"))
    return render_template("admin_kb.html")


# ============================================================
# Admin APIs
# ============================================================
@app.route("/api/admin/kb/qa/list", methods=["GET"])
@login_required
def api_admin_kb_qa_list():
    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    enabled = request.args.get("enabled", default="1")
    q = KnowledgeQA.query
    if enabled in ("0", "1"):
        q = q.filter_by(enabled=(enabled == "1"))
    rows = q.order_by(KnowledgeQA.updated_at.desc()).limit(500).all()

    data = []
    for r in rows:
        data.append(
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "tags": r.tags or "",
                "enabled": bool(r.enabled),
                "updated_at": (r.updated_at.isoformat() if r.updated_at else ""),
            }
        )
    return jsonify({"success": True, "data": data})


@app.route("/api/admin/kb/qa/create", methods=["POST"])
@login_required
def api_admin_kb_qa_create():
    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    answer = (payload.get("answer") or "").strip()
    tags = (payload.get("tags") or "").strip()
    if len(question) < 2 or len(answer) < 2:
        return jsonify({"success": False, "msg": "问题与答案不能为空"}), 400

    row = KnowledgeQA(question=question, answer=answer, tags=tags, enabled=True)
    kb_upsert_embedding_for_qa(row)
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True, "data": {"id": row.id}})


@app.route("/api/admin/kb/qa/<int:qid>/update", methods=["POST"])
@login_required
def api_admin_kb_qa_update(qid: int):
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
        return jsonify({"success": False, "msg": "问题与答案不能为空"}), 400

    row.question = question
    row.answer = answer
    row.tags = tags
    row.enabled = bool(enabled)
    kb_upsert_embedding_for_qa(row)
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/admin/kb/qa/<int:qid>/delete", methods=["POST"])
@login_required
def api_admin_kb_qa_delete(qid: int):
    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    row = db.session.get(KnowledgeQA, qid)
    if row is None:
        return jsonify({"success": False, "msg": "not_found"}), 404

    # 软删除：禁用即可（保留历史便于审计）
    row.enabled = False
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/admin/kb/rebuild_embeddings", methods=["POST"])
@login_required
def api_admin_kb_rebuild_embeddings():
    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "forbidden"}), 403

    rows = KnowledgeQA.query.order_by(KnowledgeQA.id.asc()).all()
    updated = 0
    for r in rows:
        kb_upsert_embedding_for_qa(r)
        db.session.add(r)
        updated += 1
    db.session.commit()
    return jsonify({"success": True, "data": {"updated": updated}})

@app.route("/api/admin/get_messages/<int:user_id>")
@login_required
def api_admin_get_messages(user_id: int):
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    last_id = request.args.get("last_id", default=0, type=int)
    target_user = db.session.get(User, user_id)
    if target_user is None:
        return jsonify({"status": "not_found"}), 404

    new_records = (
        ChatRecord.query.filter(ChatRecord.user_id == user_id, ChatRecord.id > last_id)
        .order_by(ChatRecord.id.asc())
        .all()
    )

    msgs = []
    for r in new_records:
        msgs.append(
            {
                "id": r.id,
                "text": r.text,
                "reply": r.reply,
                "emotion": r.emotion,
                "confidence": r.confidence,
                "timestamp": r.timestamp.isoformat(),
                "is_admin_reply": bool(r.is_admin_reply),
                "feedback": int(r.feedback or 0),
            }
        )

    return jsonify({"status": "success", "messages": msgs})


@app.route("/api/admin/reply", methods=["POST"])
@login_required
def api_admin_reply():
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    reply = (payload.get("reply") or "").strip()

    if not user_id or not reply:
        return jsonify({"status": "bad_request"}), 400

    target_user = db.session.get(User, int(user_id))
    if target_user is None:
        return jsonify({"status": "not_found"}), 404

    record = ChatRecord(
        user_id=target_user.id,
        text="",
        reply=reply,
        emotion="neutral",
        confidence=0.0,
        is_admin_reply=True,
        feedback=0,
    )
    db.session.add(record)

    db.session.commit()

    # ========== WebSocket 推送：通知用户收到人工回复 ==========
    socketio.emit('new_message', {
        'id': record.id,
        'reply': reply,
        'emotion': 'neutral',
        'confidence': 0.0,
        'timestamp': record.timestamp.isoformat(),
        'is_admin_reply': True,
        'feedback': 0,
        'intervention': False,
        'should_speak': True,
    }, room=f'user_{target_user.id}')

    # 通知管理员仪表盘有新对话活动
    socketio.emit('admin_notification', {
        'type': 'new_admin_reply',
        'user_id': target_user.id,
        'username': target_user.username,
        'message': '用户收到人工回复'
    }, room='admin_room')

    return jsonify({"status": "success", "record_id": record.id})


@app.route("/api/admin/update_user_tags", methods=["POST"])
@login_required
def api_admin_update_user_tags():
    """管理员更新用户标签"""
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    tags = (payload.get("tags") or "").strip()

    if not user_id:
        return jsonify({"status": "bad_request", "msg": "缺少 user_id"}), 400

    target_user = db.session.get(User, int(user_id))
    if target_user is None:
        return jsonify({"status": "not_found", "msg": "用户不存在"}), 404

    target_user.persona_tags = tags if tags else None
    db.session.commit()
    return jsonify({"status": "success", "tags": target_user.persona_tags or ""})


@app.route("/api/admin/resolve_user", methods=["POST"])
@login_required
def api_admin_resolve_user():
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    if not user_id:
        return jsonify({"status": "bad_request"}), 400

    target_user = db.session.get(User, int(user_id))
    if target_user is None:
        return jsonify({"status": "not_found"}), 404

    target_user.needs_intervention = False
    target_user.risk_counter = 0
    target_user.intervention_notified = False
    db.session.add(target_user)
    db.session.commit()
    return jsonify({"status": "success"})


# ============================================================
# FAQ (常见问题) API
# ============================================================
@app.route("/api/faq", methods=["GET"])
def api_faq_list():
    """返回常见问题列表（从知识库中筛选，标记为 FAQ 类别的条目）"""
    faqs = KnowledgeQA.query.filter_by(category='faq').order_by(KnowledgeQA.id.asc()).all()
    if not faqs:
        # 如果没有显式标记 FAQ 类别，则返回最近创建的10条知识
        faqs = KnowledgeQA.query.order_by(KnowledgeQA.id.desc()).limit(10).all()
    return jsonify({
        'status': 'success',
        'faqs': [{
            'id': f.id,
            'question': f.question,
            'answer': f.answer,
        } for f in faqs]
    })


@app.route("/api/faq/<int:faq_id>", methods=["GET"])
def api_faq_detail(faq_id: int):
    """获取单个常见问题的答案"""
    faq = db.session.get(KnowledgeQA, faq_id)
    if not faq:
        return jsonify({'status': 'not_found', 'msg': '问题不存在'}), 404
    return jsonify({
        'status': 'success',
        'id': faq.id,
        'question': faq.question,
        'answer': faq.answer,
    })


# ============================================================
# Rating (1-5 星评分) API
# ============================================================
@app.route("/api/rating", methods=["POST"])
@login_required
def api_rating():
    """
    用户对 AI 回复进行 1-5 星评分 + 文字建议
    """
    if current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    record_id = data.get('record_id')
    rating = data.get('rating')  # 1-5 星
    suggestion = (data.get('suggestion') or '').strip()

    if not record_id:
        return jsonify({'status': 'error', 'msg': '缺少 record_id'}), 400

    # 校验评分范围 (1-5)
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'msg': '评分必须是 1-5 之间的整数'}), 400

    if suggestion and len(suggestion) > 500:
        return jsonify({'status': 'error', 'msg': '建议内容不能超过500字'}), 400

    record = db.session.get(ChatRecord, int(record_id))
    if not record or record.user_id != current_user.id:
        return jsonify({'status': 'not_found', 'msg': '记录不存在'}), 404

    # 存储评分到独立的 rating 字段（1-5 星，0 表示未评分）
    record.rating = rating
    db.session.commit()

    return jsonify({
        'status': 'success',
        'rating': rating,
        'msg': '感谢您的反馈！'
    })


# ============================================================
# Transfer-to-human 意图识别 API
# ============================================================
TRANSFER_KEYWORDS = [
    "转人工", "人工客服", "人工服务", "转接人工",
    "我要找人", "找人工", "联系客服", "人工",
    "不是机器人", "我要投诉", "找你们领导", "找经理",
    "真人", "别再机器人了", "不要AI", "不要机器人",
]

@app.route("/api/transfer_to_human", methods=["POST"])
@login_required
def api_transfer_to_human():
    """
    用户主动请求转人工客服
    """
    if current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '用户主动请求转人工').strip()

    user = db.session.get(User, current_user.id)
    if user:
        user.needs_intervention = True
        user.intervention_notified = False
        user.risk_level = user.risk_level or 'yellow'  # 保留已有的 red 级别
        db.session.commit()

        # WebSocket 通知管理员
        try:
            socketio.emit('crisis_alert', {
                'user_id': user.id,
                'username': user.username,
                'risk_level': user.risk_level,
                'message': f'用户 {user.username} 主动请求转人工：{reason}'
            }, room='admin_room')
        except Exception as ws_err:
            print(f"[WARN] WebSocket 推送失败: {ws_err}")

    return jsonify({
        'status': 'success',
        'msg': '已为您转接人工客服，请稍等。'
    })


@app.route("/api/detect_transfer_intent", methods=["POST"])
@login_required
def api_detect_transfer_intent():
    """
    检测用户消息是否包含转人工意图
    前端在发送消息前可调用此 API 快速判断
    """
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'status': 'error', 'msg': '缺少文本'}), 400

    has_intent = False
    for kw in TRANSFER_KEYWORDS:
        if kw in text:
            has_intent = True
            break

    return jsonify({
        'status': 'success',
        'transfer_intent': has_intent,
    })


# ============================================================
# Crisis intervention statistics API
# ============================================================
@app.route("/api/crisis_stats", methods=["GET"])
@login_required
def api_crisis_stats():
    """获取危机干预统计数据"""
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403
    stats = CrisisService.get_stats()
    return jsonify({
        'status': 'success',
        'yellow_warnings': stats['yellow'],
        'red_warnings': stats['red'],
        'total_interventions': stats['total'],
    })


# Quick replies CRUD
@app.route("/api/admin/quick_reply", methods=["GET"])
@login_required
def api_admin_quick_reply_list():
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    items = QuickReply.query.order_by(QuickReply.id.desc()).all()
    return jsonify(
        {
            "status": "success",
            "items": [{"id": q.id, "content": q.content} for q in items],
        }
    )


@app.route("/api/admin/quick_reply", methods=["POST"])
@login_required
def api_admin_quick_reply_create():
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"status": "bad_request"}), 400

    q = QuickReply(content=content)
    db.session.add(q)
    db.session.commit()
    return jsonify({"status": "success", "id": q.id})


@app.route("/api/admin/quick_reply/<int:qid>", methods=["PUT"])
@login_required
def api_admin_quick_reply_update(qid: int):
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"status": "bad_request"}), 400

    q = db.session.get(QuickReply, qid)
    if q is None:
        return jsonify({"status": "not_found"}), 404

    q.content = content
    db.session.add(q)
    db.session.commit()
    return jsonify({"status": "success"})


@app.route("/api/admin/quick_reply/<int:qid>", methods=["DELETE"])
@login_required
def api_admin_quick_reply_delete(qid: int):
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    q = db.session.get(QuickReply, qid)
    if q is None:
        return jsonify({"status": "not_found"}), 404

    db.session.delete(q)
    db.session.commit()
    return jsonify({"status": "success"})


@app.route('/api/admin/analyze_user/<int:user_id>', methods=['POST'])
@login_required
def api_analyze_user(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    result = analyze_user_persona(user_id)
    if result.get("success"):
        return jsonify({'success': True, 'data': result['data']})
    # 根据错误原因返回合适的 HTTP 状态码
    msg = result.get("msg", "生成失败")
    if "未配置" in msg or "未设置" in msg:
        return jsonify({'success': False, 'msg': msg}), 503  # 服务不可用
    if "不存在" in msg:
        return jsonify({'success': False, 'msg': msg}), 404
    if "数据不足" in msg:
        return jsonify({'success': False, 'msg': msg}), 400
    return jsonify({'success': False, 'msg': msg}), 500


# ============================================================
# Dashboard (admin only): page + stats api
# ============================================================
@app.route("/dashboard")
@login_required
def dashboard_page():
    if not current_user.is_admin:
        return redirect(url_for("chat_page"))
    return render_template("dashboard.html")


@app.route("/api/emotion_stats")
@login_required
def api_emotion_stats():
    if not current_user.is_admin:
        return jsonify({"status": "forbidden"}), 403

    results = (
        db.session.query(ChatRecord.emotion, db.func.count(ChatRecord.emotion))
        .filter(ChatRecord.emotion != None)  # noqa: E711
        .group_by(ChatRecord.emotion)
        .all()
    )
    stats = {emotion: int(cnt) for (emotion, cnt) in results if emotion}
    return jsonify({"status": "success", "stats": stats})


# ============================================================
# API: 退单统计 (withdrawal_stats) - 对应论文中退单分析功能
# ============================================================
@app.route('/api/withdrawal_stats', methods=['GET'])
@login_required
def api_withdrawal_stats():
    """退单/退款统计分析（管理员端）"""
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    total_refunds = RefundRequest.query.count()
    pending = RefundRequest.query.filter_by(status='待审核').count()
    approved = RefundRequest.query.filter_by(status='已批准').count()
    rejected = RefundRequest.query.filter_by(status='已拒绝').count()

    return jsonify({
        'status': 'success',
        'total_refunds': total_refunds,
        'pending': pending,
        'approved': approved,
        'rejected': rejected
    })


# ============================================================
# API: 意图统计 (intent_stats) - 对应论文第4章数据分析
# ============================================================
@app.route('/api/intent_stats', methods=['GET'])
@login_required
def api_intent_stats():
    """意图分布统计（管理员端） - 分析用户意图趋势"""
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    # 获取所有意图统计记录
    total = db.session.query(IntentStat).count()
    if total == 0:
        return jsonify({'status': 'success', 'total': 0, 'distribution': {}, 'daily_trend': []})

    # 意图分布
    intent_counts = (
        db.session.query(IntentStat.intent, db.func.count(IntentStat.id))
        .group_by(IntentStat.intent)
        .order_by(db.func.count(IntentStat.id).desc())
        .all()
    )
    distribution = {}
    for intent, cnt in intent_counts:
        distribution[intent] = int(cnt)

    # 最近7天每日意图趋势
    today = datetime.now(timezone.utc).date()
    daily_trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        count = (
            db.session.query(IntentStat)
            .filter(IntentStat.timestamp >= day_start, IntentStat.timestamp < day_end)
            .count()
        )
        daily_trend.append({'date': day.strftime('%m-%d'), 'count': count})

    return jsonify({
        'status': 'success',
        'total': total,
        'distribution': distribution,
        'daily_trend': daily_trend
    })


# ============================================================
# API: 退单预警 (refund_alert) - 对应论文的异常检测预警
# ============================================================
@app.route('/api/refund_alert', methods=['GET'])
@login_required
def api_refund_alert():
    """
    退单预警分析 - 当待审核退款数或退款率超过阈值时触发预警
    对应论文第4章：异常检测与预警发送
    """
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    total_orders = Order.query.count()
    total_refunds = RefundRequest.query.count()
    pending = RefundRequest.query.filter_by(status='待审核').count()

    # 退款率
    refund_rate = round(total_refunds / total_orders * 100, 1) if total_orders > 0 else 0.0

    # 预警规则（论文4.2.3节）：
    # - 待审核退款数 >= 5：黄色预警
    # - 退款率 >= 30%：黄色预警
    # - 待审核退款数 >= 10 或 退款率 >= 50%：红色预警
    alert_level = 'normal'
    alert_message = ''

    if pending >= 10 or refund_rate >= 50.0:
        alert_level = 'red'
        alert_message = f'退单红色预警：待审核{pending}笔，退款率{refund_rate}%。请立即安排人工处理！'
    elif pending >= 5 or refund_rate >= 30.0:
        alert_level = 'yellow'
        alert_message = f'退单黄色预警：待审核{pending}笔，退款率{refund_rate}%。请关注退款趋势。'

    # 最近7天每日退款趋势
    today = datetime.now(timezone.utc).date()
    daily_refunds = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        count = RefundRequest.query.filter(
            RefundRequest.created_at >= day_start,
            RefundRequest.created_at < day_end
        ).count()
        daily_refunds.append({'date': day.strftime('%m-%d'), 'count': count})

    # 退单原因分布
    reason_stats = (
        db.session.query(RefundRequest.reason, db.func.count(RefundRequest.id))
        .group_by(RefundRequest.reason)
        .order_by(db.func.count(RefundRequest.id).desc())
        .limit(10)
        .all()
    )
    reasons = []
    for reason, cnt in reason_stats:
        reasons.append({'reason': (reason or '')[:50], 'count': int(cnt)})

    return jsonify({
        'status': 'success',
        'alert_level': alert_level,
        'alert_message': alert_message,
        'total_orders': total_orders,
        'total_refunds': total_refunds,
        'pending': pending,
        'refund_rate': refund_rate,
        'daily_refunds': daily_refunds,
        'reason_distribution': reasons,
    })


# ============================================================
# register
# ============================================================
@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat_page"))

    if request.method == "POST":
        # 同时支持 JSON 与 form 两种请求体
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            username = (payload.get("username") or "").strip()
            password = (payload.get("password") or "").strip()
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

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

        # 检查是否已存在
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


# ============================================================
# [保留] 其他可能用到的接口 (清空历史/个人中心)
# ============================================================
@app.route('/api/history/clear', methods=['POST'])
@login_required
def api_clear_history():
    try:
        ChatRecord.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'msg': str(e)}), 500


@app.route('/api/user/profile_data')
@login_required
def api_user_profile_data():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.order_date.desc()).all()
    orders_data = [{
        'id': o.id, 'number': o.order_number, 'item': o.item_name,
        'status': o.status,
        'arrival': o.estimated_arrival.strftime('%Y-%m-%d') if o.estimated_arrival else '待定',
        'order_date': o.order_date.strftime('%Y-%m-%d') if o.order_date else ''
    } for o in orders]
    return jsonify({
        'username': current_user.username,
        'tags': current_user.get_tags(),
        'summary': current_user.persona_summary,
        'orders': orders_data
    })


# ============================================================
# API: 修改密码
# ============================================================
@app.route('/api/user/change_password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json(silent=True) or {}
    old_pw = data.get('old_password', '')
    new_pw = (data.get('new_password') or '').strip()

    if not current_user.check_password(old_pw):
        return jsonify({'status': 'error', 'msg': '原密码错误'}), 400
    if len(new_pw) < PW_MIN_LEN:
        return jsonify({'status': 'error', 'msg': f'新密码不能少于{PW_MIN_LEN}位'}), 400

    current_user.set_password(new_pw)
    db.session.commit()
    return jsonify({'status': 'success', 'msg': '密码修改成功'})


# ============================================================
# API: 退款申请（用户端）
# ============================================================
@app.route('/api/refund/apply', methods=['POST'])
@login_required
def api_refund_apply():
    if current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id')
    reason = (data.get('reason') or '').strip()

    if not reason:
        return jsonify({'status': 'error', 'msg': '请填写退款原因'}), 400

    # 可选：校验订单归属
    if order_id:
        order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
        if not order:
            return jsonify({'status': 'error', 'msg': '订单不存在'}), 404
        if order.status == '已退款':
            return jsonify({'status': 'error', 'msg': '该订单已退款'}), 400

    refund = RefundRequest(
        user_id=current_user.id,
        order_id=order_id or None,
        reason=reason,
        status='待审核',
    )
    db.session.add(refund)
    db.session.commit()
    return jsonify({'status': 'success', 'refund_id': refund.id,
                    'msg': '退款申请已提交，等待客服审核'})


@app.route('/api/refund/list', methods=['GET'])
@login_required
def api_refund_list():
    if current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    refunds = (RefundRequest.query
               .filter_by(user_id=current_user.id)
               .order_by(RefundRequest.created_at.desc())
               .all())
    result = []
    for r in refunds:
        order_info = ''
        if r.order:
            order_info = f'{r.order.item_name}（{r.order.order_number}）'
        result.append({
            'id': r.id,
            'order_info': order_info,
            'reason': r.reason,
            'status': r.status,
            'admin_note': r.admin_note or '',
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''
        })
    return jsonify({'status': 'success', 'refunds': result})


# ============================================================
# API: 退款管理（管理员端）
# ============================================================
@app.route('/api/admin/refunds', methods=['GET'])
@login_required
def api_admin_refunds():
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    from sqlalchemy.orm import joinedload
    status_filter = request.args.get('status', '')
    query = RefundRequest.query.options(
        joinedload(RefundRequest.user), joinedload(RefundRequest.order)
    )
    if status_filter:
        query = query.filter_by(status=status_filter)
    refunds = query.order_by(RefundRequest.created_at.desc()).all()

    result = []
    for r in refunds:
        order_info = ''
        if r.order:
            order_info = f'{r.order.item_name}（{r.order.order_number}）'
        result.append({
            'id': r.id, 'user_id': r.user_id,
            'username': r.user.username if r.user else '',
            'order_info': order_info, 'reason': r.reason,
            'status': r.status, 'admin_note': r.admin_note or '',
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
            'updated_at': r.updated_at.strftime('%Y-%m-%d %H:%M') if r.updated_at else ''
        })
    return jsonify({'status': 'success', 'refunds': result})


@app.route('/api/admin/refund/<int:rid>/update', methods=['POST'])
@login_required
def api_admin_refund_update(rid: int):
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    new_status = data.get('status', '')
    admin_note = (data.get('admin_note') or '').strip()

    if new_status not in ('已批准', '已拒绝'):
        return jsonify({'status': 'error', 'msg': '无效状态'}), 400

    refund = db.session.get(RefundRequest, rid)
    if refund is None:
        return jsonify({'status': 'not_found'}), 404

    # 校验：已终态的工单不允许重复审批
    if refund.status in ('已批准', '已拒绝'):
        return jsonify({'status': 'error', 'msg': f'该退款工单状态为"{refund.status}"，不能重复审批'}), 400

    refund.status = new_status
    refund.admin_note = admin_note
    refund.updated_at = datetime.now(timezone.utc)

    # 批准时同步更新订单状态
    if new_status == '已批准' and refund.order:
        refund.order.status = '已退款'

    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/admin/refunds')
@login_required
def admin_refund_page():
    if not current_user.is_admin:
        return redirect(url_for('chat_page'))
    return render_template('admin_refund.html')


# ============================================================
# API: 数据看板 - 汇总统计
# ============================================================
@app.route('/api/admin/stats_summary')
@login_required
def api_stats_summary():
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    total_users = User.query.filter_by(is_admin=False).count()
    total_messages = ChatRecord.query.filter(ChatRecord.text != '').count()

    total_feedback = ChatRecord.query.filter(ChatRecord.feedback != 0).count()
    likes = ChatRecord.query.filter_by(feedback=1).count()
    satisfaction = round(likes / total_feedback * 100, 1) if total_feedback > 0 else 0.0

    intervention_users = User.query.filter_by(is_admin=False, needs_intervention=True).count()
    intervention_rate = round(intervention_users / total_users * 100, 1) if total_users > 0 else 0.0

    ai_replies = ChatRecord.query.filter(
        ChatRecord.reply != '', ChatRecord.is_admin_reply.is_(False)
    ).count()
    admin_replies = ChatRecord.query.filter_by(is_admin_reply=True).count()

    # 最近 7 天每天消息量
    daily_data = []
    today = datetime.now(timezone.utc).date()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = ChatRecord.query.filter(
            ChatRecord.timestamp >= day_start,
            ChatRecord.timestamp < day_end,
            ChatRecord.text != ''
        ).count()
        daily_data.append({'date': day.strftime('%m-%d'), 'count': count})

    # 最近 7 天每天退款申请量
    refund_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = RefundRequest.query.filter(
            RefundRequest.created_at >= day_start,
            RefundRequest.created_at < day_end,
        ).count()
        refund_data.append({'date': day.strftime('%m-%d'), 'count': count})

    pending_refunds = RefundRequest.query.filter_by(status='待审核').count()

    return jsonify({
        'status': 'success',
        'total_users': total_users,
        'total_messages': total_messages,
        'satisfaction': satisfaction,
        'intervention_rate': intervention_rate,
        'intervention_users': intervention_users,
        'ai_replies': ai_replies,
        'admin_replies': admin_replies,
        'pending_refunds': pending_refunds,
        'daily_messages': daily_data,
        'daily_refunds': refund_data,
    })


# ============================================================
# API: 每日情感趋势
# ============================================================
@app.route('/api/emotion_daily_trend')
@login_required
def api_emotion_daily_trend():
    """获取每日情感分布趋势"""
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    # 定义所有情感类型
    emotions = ['neutral', 'happy', 'angry', 'sad', 'fear', 'surprise']

    today = datetime.now(timezone.utc).date()
    daily_emotions = []

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        day_data = {'date': day.strftime('%m-%d')}

        for emotion in emotions:
            count = ChatRecord.query.filter(
                ChatRecord.timestamp >= day_start,
                ChatRecord.timestamp < day_end,
                ChatRecord.emotion == emotion,
                ChatRecord.text != ''
            ).count()
            day_data[emotion] = count

        daily_emotions.append(day_data)

    return jsonify({
        'status': 'success',
        'daily_emotions': daily_emotions
    })


# ============================================================
# API: 导出聊天记录（CSV）
# ============================================================
@app.route('/api/admin/export/chat_records')
@login_required
def api_export_chat_records():
    import csv, io
    if not current_user.is_admin:
        return jsonify({'status': 'forbidden'}), 403

    records = (
        ChatRecord.query
        .join(User, ChatRecord.user_id == User.id)
        .add_columns(User.username)
        .order_by(ChatRecord.id.asc())
        .all()
    )

    # 中国时区 (UTC+8)，用于将数据库中的 UTC 时间转换为本地时间
    china_tz = timezone(timedelta(hours=8))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', '用户名', '用户消息', '系统回复', '情绪', '置信度',
                     '是否人工', '反馈', '时间'])
    for rec, username in records:
        # 将 UTC 时间转为中国本地时间，再格式化为 Excel 可识别的格式
        local_time = (
            rec.timestamp.astimezone(china_tz).strftime('%Y-%m-%d %H:%M:%S')
            if rec.timestamp else ''
        )
        writer.writerow([
            rec.id, username, rec.text, rec.reply, rec.emotion,
            f'{rec.confidence:.2f}',
            '是' if rec.is_admin_reply else '否',
            {1: '赞', -1: '踩', 0: '无'}.get(rec.feedback, '无'),
            local_time
        ])

    from flask import Response
    output.seek(0)
    return Response(
        '\ufeff' + output.getvalue(),   # BOM 让 Excel 正确识别 UTF-8
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=chat_records.csv'}
    )


@app.route('/api/admin/dashboard_data')
@login_required
def get_dashboard_data():
    if not current_user.is_admin:
        return jsonify({'success': False, 'msg': '无权限'}), 403

    users = User.query.filter_by(is_admin=False).all()
    all_users_data = []

    for u in users:
        # 逻辑修正：根据 needs_intervention 布尔值生成状态字符串
        status_str = 'needs_intervention' if u.needs_intervention else 'normal'

        all_users_data.append({
            'id': u.id,
            'username': u.username,
            'status': status_str,  # 前端 JS 需要这个字段
            'needs_intervention': u.needs_intervention,  # 也可以传原始布尔值
            'persona_tags': u.persona_tags or '',
            'persona_summary': u.persona_summary or '',
            'last_analyzed': u.last_analyzed.strftime('%Y-%m-%d %H:%M:%S') if u.last_analyzed else ''
        })

    # 逻辑修正：使用 needs_intervention 筛选
    flagged = [u for u in users if u.needs_intervention]
    flagged_data = [{
        'id': u.id,
        'username': u.username,
        'risk_counter': u.risk_counter
    } for u in flagged]

    return jsonify({
        'success': True,
        'all_users': all_users_data,
        'flagged_users': flagged_data
    })


# ============================================================
# Bootstrap / init
# ============================================================
def seed_defaults():
    """按环境变量开关初始化演示数据（默认关闭）"""
    enable_demo_seed = os.environ.get("ENABLE_DEMO_SEED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enable_demo_seed:
        print("已跳过默认演示账号初始化（ENABLE_DEMO_SEED 未开启）")
        return

    admin_username = os.environ.get("DEMO_ADMIN_USERNAME", "admin").strip()
    admin_password = os.environ.get("DEMO_ADMIN_PASSWORD")
    user_username = os.environ.get("DEMO_USER_USERNAME", "user1").strip()
    user_password = os.environ.get("DEMO_USER_PASSWORD")

    if not admin_password or not user_password:
        raise RuntimeError(
            "ENABLE_DEMO_SEED=true 时，必须设置 DEMO_ADMIN_PASSWORD 与 DEMO_USER_PASSWORD。"
        )

    # 1. 初始化管理员账号
    if not User.query.filter_by(username=admin_username).first():
        admin = User(username=admin_username, is_admin=True)
        admin.set_password(admin_password)
        db.session.add(admin)
        print(f"已创建演示管理员: {admin_username}")

    # 2. 初始化普通测试账号
    user1 = User.query.filter_by(username=user_username).first()
    if not user1:
        user1 = User(username=user_username, is_admin=False)
        user1.set_password(user_password)
        db.session.add(user1)
        db.session.commit()  # 需要先 commit 拿到 id
        print(f"已创建演示用户: {user_username}")

    # [新增] 检查 user1 是否有订单，没有则创建测试订单
    if user1:
        if not Order.query.filter_by(user_id=user1.id).first():
            o1 = Order(
                user_id=user1.id,
                order_number="OD-2024001",
                item_name="高性能机械键盘 Pro",
                status="已发货",
                estimated_arrival=datetime.now(timezone.utc) + timedelta(days=2)
            )
            o2 = Order(
                user_id=user1.id,
                order_number="OD-2024002",
                item_name="4K 144Hz 显示器",
                status="运输中",
                estimated_arrival=datetime.now(timezone.utc) + timedelta(days=5)
            )
            db.session.add_all([o1, o2])
            print(">>> 已为 user1 生成测试订单数据")

    # 3. [新增] 预置知识库 Q&A（用于 RAG 演示）
    if not KnowledgeQA.query.first():
        preset_qas = [
            {
                "question": "怎么申请退款？",
                "answer": "打开聊天页右上角【个人中心】→【退款申请】→选择订单（可不选）→填写原因提交。管理员审核通过后会更新退款状态。",
                "tags": "退款,流程,售后",
            },
            {
                "question": "退款多久到账？",
                "answer": "一般审核通过后 1-3 个工作日原路退回（具体以支付渠道到账时间为准）。你可以在【个人中心】→【退款列表】查看进度。",
                "tags": "退款,到账,进度",
            },
            {
                "question": "怎么查询物流/订单？",
                "answer": "你可以直接在聊天框输入“查询订单/物流/到哪了”，系统会显示你的订单卡片与预计到货时间；也可在【个人中心】查看订单列表。",
                "tags": "订单,物流,查询",
            },
            {
                "question": "我想修改收货地址怎么办？",
                "answer": "如果订单还未发货/未出库，可以提供订单号与新地址，我们会尝试协助修改；若已发货通常无法改址，可联系承运方或申请退换。",
                "tags": "地址,改址,订单",
            },
            {
                "question": "一直没发货怎么办？",
                "answer": "请先提供订单号/截图，我们会核对仓库与物流状态；如超过承诺发货时效，可申请加急或退款（在【个人中心】→【退款申请】）。",
                "tags": "发货,催单,退款",
            },
            {
                "question": "商品有质量问题怎么处理？",
                "answer": "请提供问题照片/视频与订单号，我们会优先给你安排换货/退货方案；如需退款也可以在【个人中心】提交退款原因。",
                "tags": "售后,质量,退换",
            },
            {
                "question": "可以开发票吗？",
                "answer": "可以。请提供订单号、开票抬头、税号与邮箱/接收方式，我们会在核实后为你开具电子发票。",
                "tags": "发票,开票,订单",
            },
            {
                "question": "怎么联系人工客服？",
                "answer": "当系统检测到你需要人工协助时会自动转接；你也可以在聊天里说明“转人工/人工客服”，并留下订单号与问题要点，我们会尽快处理。",
                "tags": "人工,转接,帮助",
            },
        ]
        for qa in preset_qas:
            row = KnowledgeQA(
                question=qa["question"],
                answer=qa["answer"],
                tags=qa.get("tags", ""),
                enabled=True,
            )
            kb_upsert_embedding_for_qa(row)
            db.session.add(row)
        print(f">>> 已预置知识库 Q&A：{len(preset_qas)} 条")

    # 4. [新增] 预置快捷回复（用于管理员快速响应）
    if not QuickReply.query.first():
        preset_quick_replies = [
            "您好，欢迎光临！我是智能客服小C，有什么可以帮助您的吗？😊",
            "您的订单我们已经查到了，目前正在加急处理中，请您耐心等待。",
            "非常抱歉给您带来不好的体验，我们一定会尽快为您解决问题。",
            "您可以打开【个人中心】→【退款申请】，填写退款原因后提交，管理员会尽快审核。",
            "我们已经为您登记了退货/换货申请，预计 1-2 个工作日内会有工作人员与您联系。",
            "请提供您的订单号，我来帮您查询物流状态和预计到货时间。",
            "关于物流延迟的问题，我们已经联系了快递公司催促加急配送，请您谅解。",
            "如果您对商品不满意，可以在签收后 7 天内申请无理由退换货哦。",
            "感谢您的理解与支持！如果还有其他问题，随时可以找我。祝您生活愉快！",
            "人工客服已介入，我将把您的问题转交给专业客服人员处理，请稍等片刻。",
        ]
        for qr_content in preset_quick_replies:
            db.session.add(QuickReply(content=qr_content))
        print(f">>> 已预置快捷回复：{len(preset_quick_replies)} 条")

    db.session.commit()


# ============================================================
# WebSocket 事件处理
# ============================================================
connected_users = {}  # {sid: user_id}
connected_admins = set()  # 存储已连接的管理员 session_id


@socketio.on('connect')
def on_connect():
    """客户端连接时调用"""
    print(f"[SocketIO] 客户端连接: {request.sid}")


@socketio.on('disconnect')
def on_disconnect():
    """客户端断开连接时调用"""
    sid = request.sid
    if sid in connected_users:
        user_id = connected_users.pop(sid)
        print(f"[SocketIO] 用户 {user_id} 断开连接")
        leave_room(f'user_{user_id}')
    if sid in connected_admins:
        connected_admins.remove(sid)
        leave_room('admin_room')
        print(f"[SocketIO] 管理员断开连接")


@socketio.on('join')
def on_join(data):
    """Join a Socket.IO room after validating session ownership."""
    user_type = (data or {}).get('type')
    sid = request.sid

    from flask_login import current_user as cu
    if not cu.is_authenticated:
        emit('joined', {'status': 'error', 'msg': 'not authenticated'})
        return

    if user_type == 'user':
        try:
            requested_user_id = int((data or {}).get('user_id'))
        except (TypeError, ValueError):
            emit('joined', {'status': 'error', 'msg': 'invalid user_id'})
            return

        if cu.is_admin or requested_user_id != int(cu.id):
            emit('joined', {'status': 'error', 'msg': 'forbidden'})
            return

        join_room(f'user_{requested_user_id}')
        connected_users[sid] = requested_user_id
        logger.info("SocketIO user %s joined room", requested_user_id)
        emit('joined', {'status': 'connected', 'room': f'user_{requested_user_id}'})
        return

    if user_type == 'admin':
        if not cu.is_admin:
            emit('joined', {'status': 'error', 'msg': 'forbidden'})
            return

        join_room('admin_room')
        connected_admins.add(sid)
        logger.info("SocketIO admin joined admin_room")
        emit('joined', {'status': 'connected', 'room': 'admin_room'})
        return

    emit('joined', {'status': 'error', 'msg': 'invalid room type'})

@socketio.on('leave')
def on_leave(data):
    """客户端主动离开房间"""
    user_type = data.get('type')
    sid = request.sid

    if user_type == 'user':
        user_id = data.get('user_id')
        if user_id:
            leave_room(f'user_{user_id}')
            if sid in connected_users:
                connected_users.pop(sid)
    elif user_type == 'admin':
        leave_room('admin_room')
        if sid in connected_admins:
            connected_admins.remove(sid)


@socketio.on('typing')
def on_typing(data):
    """用户正在输入"""
    user_id = data.get('user_id')
    if user_id:
        # 通知管理员该用户正在输入
        emit('user_typing', {
            'user_id': user_id,
            'typing': data.get('typing', True)
        }, room='admin_room', include_self=False)


@socketio.on('request_dashboard_refresh')
def on_request_dashboard_refresh():
    """管理员请求刷新仪表盘数据"""
    # 重新获取统计数据并推送
    try:
        total_users = User.query.filter_by(is_admin=False).count()
        total_messages = ChatRecord.query.filter(ChatRecord.text != '').count()

        total_feedback = ChatRecord.query.filter(ChatRecord.feedback != 0).count()
        likes = ChatRecord.query.filter_by(feedback=1).count()
        satisfaction = round(likes / total_feedback * 100, 1) if total_feedback > 0 else 0.0

        pending_refunds = RefundRequest.query.filter_by(status='待审核').count()
        flagged_users = User.query.filter_by(is_admin=False, needs_intervention=True).count()

        emit('dashboard_data', {
            'total_users': total_users,
            'total_messages': total_messages,
            'satisfaction': satisfaction,
            'pending_refunds': pending_refunds,
            'flagged_users': flagged_users
        })
    except Exception as e:
        print(f"[ERROR] dashboard refresh failed: {e}")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        _ensure_indexes()  # 确保数据库索引存在
        seed_defaults()
        load_emotion_model()
        _register_sqlite_pragma()  # 🔴【修复】注册 SQLite WAL 模式 pragma

    debug_mode = os.environ.get("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

    print("=" * 50)
    print("[SmartCS] Smart Customer Service System Starting...")
    print("=" * 50)
    print(f"[INFO] Mode: Flask-SocketIO + {_flask_socketio_async_mode}")
    print("[INFO] WebSocket: Enabled")
    print(f"[INFO] Debug Mode: {'ON' if debug_mode else 'OFF'}")
    print("=" * 50)

    # 使用 socketio.run() 替代 app.run() 以支持 WebSocket
    socketio.run(
        app,
        host="127.0.0.1",
        port=5000,
        debug=debug_mode,
        allow_unsafe_werkzeug=debug_mode
    )