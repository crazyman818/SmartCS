# SmartCS — 智能客服系统（Smart Customer Service System）

基于深度学习的智能电商客服系统，集成 BERT 情感分析、LLM 对话生成、RAG 知识库检索、实时 WebSocket 通信和危机干预机制。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask + Flask-SQLAlchemy + Flask-Login + Flask-SocketIO |
| LLM | DeepSeek API（OpenAI 兼容接口） |
| 情感分析 | BERT（chinese-macbert-base）微调 6 分类 + 自定义改进架构 |
| 向量检索 | Sentence-Transformers（RAG），失败自动降级关键词匹配 |
| 前端 | Jinja2 模板 + 原生 JS + Socket.IO + Chart.js |
| 数据库 | SQLite（WAL 模式） |

## 快速开始

### 1. 环境要求
- Python 3.10+
- pip

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 获取模型文件

大模型文件因 GitHub 限制未包含在仓库中，需要单独下载：

**MacBERT 预训练模型**（放置于 `models/chinese-macbert-base/`）：
```bash
# 使用 HuggingFace 自动下载
python -c "from transformers import BertModel; BertModel.from_pretrained('hfl/chinese-macbert-base', cache_dir='models/chinese-macbert-base')"
```

**微调后的情感分析模型**（放置于 `models/my_finetuned_bert/`）：
- 运行 `python models/train_bert.py` 自行训练
- 或联系作者获取预训练权重

模型文件列表：
```
models/chinese-macbert-base/
  ├── config.json
  ├── vocab.txt
  ├── tokenizer.json
  └── pytorch_model.bin      # 需下载 (~393MB)

models/my_finetuned_bert/
  ├── config.json
  ├── vocab.txt
  ├── tokenizer.json
  └── model.safetensors       # 需下载或训练 (~405MB)
```

### 4. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等配置
```

### 5. 启动
```bash
python app.py
```
访问 `http://127.0.0.1:5000`

## 核心功能

- **6 分类情感识别**（中性/开心/愤怒/悲伤/恐惧/惊讶）— BERT + 改进的多头注意力池化架构
- **智能意图识别** — 12+ 意图类别（订单/物流/退款/投诉/转人工等）
- **RAG 知识库检索** — 向量检索增强 LLM 回复质量
- **三级危机干预** — 黄色预警（连续负面）→ 红色预警（极端关键词）→ 自动转人工
- **实时 WebSocket** — 消息推送、输入状态、预警通知
- **用户画像** — LLM 自动生成用户标签和摘要
- **数据仪表盘** — 情感分布、意图趋势、退单预警、满意度统计
- **退款工单管理** — 用户申请 → 管理员审批全流程

## 项目结构

```
SmartCS/
├── app.py                       # 主应用（路由、模型、业务逻辑）
├── evaluate.py                  # 情感模型评估脚本
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
├── models/
│   ├── train_bert.py            # BERT 训练脚本
│   ├── improved_bert_model.py   # 改进的 BERT 架构（多头注意力 + 自注意力池化）
│   ├── chinese-macbert-base/    # 预训练模型（需下载）
│   └── my_finetuned_bert/       # 微调后模型（需训练/下载）
├── templates/                   # Jinja2 页面模板（9 个）
├── static/                      # CSS/JS 前端资源
├── data/                        # 训练/评估/测试数据集
└── tests/                       # 测试用例
```

## 演示账号

启用 `ENABLE_DEMO_SEED=true` 后自动创建：
- 管理员：通过 `DEMO_ADMIN_USERNAME` / `DEMO_ADMIN_PASSWORD` 配置
- 普通用户：通过 `DEMO_USER_USERNAME` / `DEMO_USER_PASSWORD` 配置

## License

仅供学习和研究使用。
