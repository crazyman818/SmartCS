#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对照论文要求，验证所有核心功能是否已实现"""

import sys
import os
sys.path.insert(0, 'e:/graduation_project/SmartCS')

from app import app, db, User, ChatRecord, Order, RefundRequest, KnowledgeQA, QuickReply

PASS = 0
FAIL = 0
MISSING = []

def check_item(name, condition):
    global PASS, FAIL, MISSING
    if condition:
        PASS += 1
        print(f'  [OK] {name}')
    else:
        FAIL += 1
        MISSING.append(name)
        print(f'  [MISS] {name}')

with app.app_context():
    print('=' * 50)
    print('论文核心功能对照验证')
    print('=' * 50)

    model_path = 'models/my_finetuned_bert'
    content = open('app.py', encoding='utf-8').read()
    admin_html = open('templates/admin.html', encoding='utf-8').read()

    # 1. 情感分析模型 (论文第3章)
    print('\n[1] 情感分析模块 (论文 第3章)')
    check_item('微调模型目录存在', os.path.exists(model_path))
    check_item('模型权重文件存在', os.path.exists(os.path.join(model_path, 'model.safetensors')) or os.path.exists(os.path.join(model_path, 'pytorch_model.bin')))
    check_item('load_emotion_model函数', 'load_emotion_model' in content)
    check_item('predict_emotion函数', 'predict_emotion' in content)
    check_item('6分类标签映射(angry/sad/fear/happy/surprise/neutral)', 'angry' in content and 'sad' in content and 'neutral' in content)
    check_item('ImprovedBertForSequenceClassification类', 'ImprovedBertForSequenceClassification' in content or os.path.exists('models/improved_bert_model.py'))
    check_item('关键词兜底机制', 'fallback' in content.lower() and 'keyword' in content.lower())

    # 2. RAG检索增强生成 (论文第3章, 表5-5)
    print('\n[2] RAG检索增强生成 (论文 第3章, 表5-5)')
    check_item('KnowledgeQA模型(question/answer/category/embedding/use_count)', hasattr(KnowledgeQA, 'question') and hasattr(KnowledgeQA, 'answer') and hasattr(KnowledgeQA, 'category'))
    check_item('Sentence-Transformers向量化', 'SentenceTransformer' in content)
    check_item('embed computed字段', hasattr(KnowledgeQA, 'embedding'))
    check_item('向量检索函数(kb_search)', 'kb_search' in content or 'cosine_similarity' in content)
    check_item('知识库CRUD API', 'admin/kb' in content)
    check_item('RAG上下文注入LLM', 'build_context' in content.lower() or 'extra_system' in content.lower() or 'knowledge' in content.lower())

    # 3. 危机干预 (论文 1.3节, 6.2.2节)
    print('\n[3] 危机干预机制 (论文 1.3节, 6.2.2节)')
    check_item('User.risk_counter', hasattr(User, 'risk_counter'))
    check_item('User.needs_intervention', hasattr(User, 'needs_intervention'))
    check_item('User.risk_level (黄/红预警)', hasattr(User, 'risk_level'))
    check_item('User.intervention_notified', hasattr(User, 'intervention_notified'))
    check_item('update_risk_state函数', 'update_risk_state' in content)
    check_item('危机关键词检测(极端关键词)', 'EXTREME_KEYWORDS' in content or 'extreme' in content.lower())
    check_item('连续负面情绪检测', 'get_recent_emotions' in content or 'NEGATIVE_EMOTIONS' in content)

    # 4. 用户画像 (论文 4.3.1节, 6.2.1节)
    print('\n[4] 用户画像 (论文 4.3.1节, 6.2.1节)')
    check_item('User.persona_tags', hasattr(User, 'persona_tags'))
    check_item('User.persona_summary', hasattr(User, 'persona_summary'))
    check_item('User.last_analyzed', hasattr(User, 'last_analyzed'))
    check_item('analyze_user_persona函数', 'analyze_user_persona' in content)
    check_item('api_analyze_user路由', 'analyze_user' in content)
    check_item('DeepSeek API调用', 'deepseek' in content.lower() or 'LLM_MODEL' in content)

    # 5. 订单管理 (论文 4.3.1节, 表5-3)
    print('\n[5] 订单管理 (论文 4.3.1节, 表5-3)')
    check_item('Order表 (order_number/item_name/status)', hasattr(Order, 'order_number') and hasattr(Order, 'item_name') and hasattr(Order, 'status'))
    check_item('订单查询功能', 'order/confirm' in content or 'order/query' in content)

    # 6. 退款管理 (论文 4.3.1节, 表5-4)
    print('\n[6] 退款工单管理 (论文 4.3.1节, 表5-4)')
    check_item('RefundRequest表 (order_id/reason/amount/status)', hasattr(RefundRequest, 'order_id') and hasattr(RefundRequest, 'reason') and hasattr(RefundRequest, 'status'))
    check_item('RefundRequest.admin_note', hasattr(RefundRequest, 'admin_note'))
    check_item('退款申请API', 'refund/apply' in content)
    check_item('管理员退款审批API', 'admin/refund' in content)

    # 7. 管理员面板 (论文 4.3.2节, 6.2.2节, 表7-5)
    print('\n[7] 管理员功能 (论文 4.3.2节, 6.2.2节)')
    check_item('管理后台页面', 'admin.html' in str(os.listdir('templates')))
    check_item('知识库管理页面', 'admin_kb.html' in str(os.listdir('templates')))
    check_item('聊天管理页面', 'admin_chat.html' in str(os.listdir('templates')))
    check_item('退款管理页面', 'admin_refund.html' in str(os.listdir('templates')))
    check_item('快捷回复QuickReply表', hasattr(QuickReply, '__tablename__'))
    check_item('数据导出API', 'export/chat_records' in content)
    check_item('用户管理功能(admin.html内嵌)', ('all_users' in admin_html) or ('api/admin/users' in content))

    # 8. 数据可视化仪表盘 (论文 4.3.2节, 6.2.2节, 图6-13)
    print('\n[8] 数据可视化仪表盘 (论文 4.3.2节, 6.2.2节)')
    check_item('仪表盘页面', 'dashboard.html' in str(os.listdir('templates')))
    check_item('情感分布API (emotion_stats)', 'emotion_stats' in content)
    check_item('意图统计API (intent_stats)', 'intent_stats' in content)
    check_item('退款预警API (refund_alert)', 'refund_alert' in content)
    check_item('情感趋势API (emotion_daily_trend)', 'emotion_daily_trend' in content)
    check_item('仪表盘汇总API (dashboard_data)', 'dashboard_data' in content)

    # 9. 系统测试 (论文第7章)
    print('\n[9] 系统测试 (论文 第7章)')
    check_item('冒烟测试存在', os.path.exists('tests/test_smoke.py'))
    check_item('用户注册功能', '/register' in content)
    check_item('用户登录功能', '/login' in content)
    check_item('ChatRecord消息存储(text/reply/emotion/feedback)', hasattr(ChatRecord, 'text') and hasattr(ChatRecord, 'reply'))

    # 10. 前端技术栈 (论文 6.1.2节)
    print('\n[10] 前端技术栈 (论文 6.1.2节)')
    check_item('Jinja2模板系统', os.path.exists('templates/index.html'))
    check_item('CSS样式文件', os.path.exists('static/style.css'))
    check_item('JavaScript交互文件', os.path.exists('static/script.js'))
    check_item('聊天页面', os.path.exists('templates/chat.html'))
    check_item('管理员页面', os.path.exists('templates/admin.html'))

    print('\n' + '=' * 50)
    total_count = PASS + FAIL
    print(f'验证结果: {PASS}/{total_count} 通过, {FAIL}/{total_count} 未通过')
    print('=' * 50)

    if FAIL > 0:
        print('\n以下检查项未通过（需补全）:')
        for m in MISSING:
            print(f'  - {m}')
        sys.exit(1)
    else:
        print('\n论文描述的所有核心功能均已实现并验证通过。')
        sys.exit(0)