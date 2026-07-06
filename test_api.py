import urllib.request
import urllib.parse
import http.cookiejar
import json

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Test login
data = urllib.parse.urlencode({'username': 'user1', 'password': '123456'}).encode()
try:
    req = urllib.request.Request('http://127.0.0.1:5000/login', data=data, method='POST')
    resp = opener.open(req)
    print(f'Login: {resp.status} - {resp.geturl()}')
except Exception as e:
    print(f'Login ERROR: {e}')
    exit(1)

# Test chat API
data = json.dumps({'text': '我的订单到哪里了'}).encode()
try:
    req = urllib.request.Request(
        'http://127.0.0.1:5000/api/chat',
        data=data,
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    resp = opener.open(req)
    result = json.loads(resp.read())
    status = result.get('status')
    emotion = result.get('emotion')
    reply = (result.get('reply') or '')[:80]
    orders = result.get('orders_data')
    print(f'Chat API: status={status}, emotion={emotion}')
    print(f'  reply: {reply}...')
    print(f'  orders: {orders}')
except Exception as e:
    print(f'Chat API ERROR: {e}')

# Test emotion detection directly
data = json.dumps({'text': '我真的很生气，你们的服务太差了！'}).encode()
try:
    req = urllib.request.Request(
        'http://127.0.0.1:5000/api/chat',
        data=data,
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    resp = opener.open(req)
    result = json.loads(resp.read())
    print(f'\nAngry test: status={result.get("status")}, emotion={result.get("emotion")}')
except Exception as e:
    print(f'Angry test ERROR: {e}')

# Test FAQ API
try:
    req = urllib.request.Request('http://127.0.0.1:5000/api/faq')
    resp = opener.open(req)
    result = json.loads(resp.read())
    print(f'\nFAQ API: status={result.get("status")}, count={len(result.get("faqs", []))}')
except Exception as e:
    print(f'FAQ API ERROR: {e}')

print('\nAll tests completed!')