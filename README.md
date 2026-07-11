# SmartCS - 智能客服系统

SmartCS 是一个基于 Flask 的智能电商客服系统，集成用户登录、实时聊天、BERT 情绪识别、LLM 回复、RAG 知识库、危机干预、管理员接入、退款工单和数据看板。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | Flask, Flask-SQLAlchemy, Flask-Login, Flask-SocketIO |
| AI 回复 | DeepSeek / OpenAI 兼容接口 |
| 情绪识别 | PyTorch, Transformers, Chinese MacBERT 微调模型 |
| RAG | Sentence-Transformers 向量检索，失败时降级为关键词检索 |
| 前端 | Jinja2, 原生 JavaScript, Socket.IO, Chart.js |
| 数据库 | SQLite，默认位于 `instance/site.db` |

## 工程化结构

重构后新增 `smartcs/` 包作为应用入口和共享基础设施：

```text
smartcs/
  __init__.py          # create_app(config_name=None)
  config.py            # development/testing/production 配置
  extensions.py        # db/login/csrf/limiter/socketio 扩展实例
  legacy_app.py        # 兼容层，保留现有路由并逐步迁移
  models.py            # 模型导出入口
  services/            # 新增或迁移后的服务模块
  repositories/        # Repository 导出入口
  routes/              # 后续 Blueprint 迁移目标
  socket_handlers.py   # Socket.IO handler 导出入口
```

`app.py` 现在只作为本地兼容启动入口，推荐生产环境从 `wsgi.py` 导入：

```python
from wsgi import app, socketio
```

## 快速开始

### 1. 创建并安装依赖

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，至少设置：

```env
SECRET_KEY=replace-with-a-long-random-secret
LLM_API_KEY=sk-your-api-key
```

开发模式如果未配置 `LLM_API_KEY`，系统会自动降级为兜底回复。生产环境必须设置 `SECRET_KEY`。

### 3. 准备模型文件

默认情绪模型目录：

```text
models/my_finetuned_bert/
```

如果只做接口测试或页面调试，可以设置：

```env
LOAD_EMOTION_MODEL_ON_STARTUP=false
```

### 4. 启动

```bash
python app.py
```

访问：`http://127.0.0.1:5000`

## 测试

基础测试：

```bash
.\.venv\Scripts\python.exe -m pytest
```

覆盖率测试需要安装 `pytest-cov`，已写入 `requirements.txt`：

```bash
.\.venv\Scripts\python.exe -m pytest --cov=smartcs --cov=services --cov=repositories --cov=utils
```

当前测试重点覆盖：

- `create_app("testing")` 测试配置
- 管理员 API 权限边界
- Socket.IO 房间加入鉴权
- 意图识别、LLM 降级回复、危机干预服务

## 安全配置

- Session 默认启用 `HttpOnly` 与 `SameSite=Lax`。
- JSON 写接口沿用登录态保护，`WTF_CSRF_CHECK_DEFAULT=false`，后续可按接口逐步启用 CSRF token。
- Socket.IO 房间加入会校验用户归属，普通用户不能加入其他用户房间或管理员房间。
- `SOCKETIO_CORS_ALLOWED_ORIGINS` 默认限制到本地开发地址，生产环境请显式配置实际域名。
- 应用响应默认添加 `X-Content-Type-Options`、`X-Frame-Options` 和 `Referrer-Policy`。

## 常用环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SMARTCS_ENV` | `development` | 可选 `development`、`testing`、`production` |
| `SECRET_KEY` | 开发默认值 | 生产环境必填 |
| `DATABASE_URL` | `sqlite:///site.db` | 数据库连接 URI |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口地址 |
| `LLM_API_KEY` | 空 | LLM API Key，空则降级回复 |
| `LLM_MODEL` | `deepseek-chat` | LLM 模型名 |
| `SOCKETIO_ASYNC_MODE` | `eventlet` | Windows 可改为 `threading` |
| `SOCKETIO_CORS_ALLOWED_ORIGINS` | 本地地址 | 逗号分隔的允许来源 |
| `LOAD_EMOTION_MODEL_ON_STARTUP` | `true` | 是否启动时加载 BERT 模型 |
| `ENABLE_DEMO_SEED` | `true` | 是否初始化演示数据 |

## 迁移说明

当前重构保留所有既有 URL、模板路径和主要 JSON 字段。`smartcs/legacy_app.py` 是兼容层，后续新增功能应优先放入 `smartcs/services`、`smartcs/repositories` 和 `smartcs/routes`，再逐步把旧路由迁入 Blueprint。
