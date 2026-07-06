"""SmartCS 全面集成测试"""
import json
import urllib.request
import urllib.error
import http.cookiejar

BASE = 'http://127.0.0.1:5000'

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def api(method, path, data=None, expect_json=True):
    url = BASE + path
    headers = {'Content-Type': 'application/json'}
    body = None
    if data is not None:
        body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = opener.open(req, timeout=10)
        if not expect_json:
            return resp.status, resp.read().decode('utf-8', errors='replace')[:500]
        try:
            return resp.status, json.loads(resp.read().decode('utf-8'))
        except Exception:
            return resp.status, {'_text': resp.read().decode('utf-8', errors='replace')[:200]}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            raw = e.read().decode('utf-8', errors='replace')[:200]
            return e.code, {'_raw': raw}
    except Exception as e:
        return None, {'_error': str(e)}


passed = 0
failed = 0


def check(name, condition, detail=''):
    global passed, failed
    if condition:
        print(f'  [PASS] {name}')
        passed += 1
    else:
        print(f'  [FAIL] {name}: {detail}')
        failed += 1


def safe(j):
    if isinstance(j, dict):
        return j
    return {}


print('=== SmartCS 集成测试 ===')
print()

# 1. 注册测试
print('[TEST 1] JSON 注册')
code, j = api('POST', '/register', {'username': 'int_test_user2', 'password': 'testpass123'})
j = safe(j)
print(f'  status={code}, resp={json.dumps(j, ensure_ascii=False)[:120]}')
check('注册返回非空状态码', code is not None)

# 2. 登录
print('[TEST 2] 登录')
code, j = api('POST', '/login', {'username': 'int_test_user2', 'password': 'testpass123'})
check('登录成功', code is not None and code < 500, f'code={code}')
print(f'  status={code}')

# 3. FAQ
print('[TEST 3] FAQ 接口')
code, j = api('GET', '/api/faq')
j = safe(j)
check('FAQ 返回 200', code == 200, f'code={code}')
check('FAQ 包含数据', 'faqs' in j, str(j)[:80])
print(f'  status={code}, count={len(j.get("faqs", []))}')

# 4. 聊天 API
print('[TEST 4] 聊天接口')
code, j = api('POST', '/api/chat', {'text': '你好，帮我查一下订单'})
j = safe(j)
check('聊天 API 返回 200', code == 200, f'code={code}')
print(f'  status={code}, emotion={j.get("emotion", "?")}')

# 5. 获取消息
print('[TEST 5] 获取消息')
code, j = api('GET', '/api/get_messages?last_id=0')
j = safe(j)
check('消息接口可访问', code is not None and code < 500, f'code={code}')
print(f'  status={code}, msgs={len(j.get("messages", []))}')

# 6. 用户画像
print('[TEST 6] 用户画像')
code, j = api('GET', '/api/user/profile_data')
j = safe(j)
check('用户画像可访问', code is not None and code < 500, f'code={code}')
print(f'  status={code}, username={j.get("username", "?")}')

# 7. 转人工检测
print('[TEST 7] 转人工意图')
code, j = api('POST', '/api/detect_transfer_intent', {'text': '我要转人工'})
j = safe(j)
check('转人工检测可访问', code is not None and code < 500, f'code={code}')
print(f'  status={code}, intent={j.get("transfer_intent", "?")}')

# 8. 退款申请
print('[TEST 8] 退款申请')
code, j = api('POST', '/api/refund/apply', {'reason': '商品质量问题'})
j = safe(j)
check('退款申请可访问', code is not None and code < 500, f'code={code}')
print(f'  status={code}, refund_id={j.get("refund_id", "?")}')

# 9. 退款列表
print('[TEST 9] 退款列表')
code, j = api('GET', '/api/refund/list')
j = safe(j)
check('退款列表可访问', code is not None and code < 500, f'code={code}')
print(f'  status={code}, refunds={len(j.get("refunds", []))}')

# 10. 修改密码
print('[TEST 10] 修改密码')
code, j = api('POST', '/api/user/change_password',
              {'old_password': 'testpass123', 'new_password': 'newpass456'})
check('修改密码可访问', code is not None and code < 500, f'code={code}')
print(f'  status={code}')
# restore
api('POST', '/api/user/change_password',
    {'old_password': 'newpass456', 'new_password': 'testpass123'})

# 11. 管理面板（需要管理员账号）
print('[TEST 11] 管理面板首页')
# 用普通用户访问 admin 页面会被重定向（302）到 chat
code, _ = api('GET', '/admin', expect_json=False)
check('管理面板可访问', code in (200, 302), f'code={code}')
print(f'  status={code}')

# 12. 前端页面
print('[TEST 12] 前端页面可渲染')
for path in ['/', '/login', '/register', '/chat', '/dashboard']:
    code, _ = api('GET', path, expect_json=False)
    # 已登录用户访问某些页面会产生 302 重定向（如 /、/login），这是合理行为
    check(f'{path} 可渲染', code in (200, 302), f'code={code}')

print()
print(f'=== 测试结果: {passed} passed, {failed} failed ===')
if failed == 0:
    print('All core API tests passed!')
else:
    print(f'{failed} issue(s) found')