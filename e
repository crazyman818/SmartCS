"""SmartCS 冒烟测试 v2 - 使用正确的 API 路径"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ['ENABLE_DEMO_SEED'] = 'false'
os.environ['FLASK_DEBUG'] = '1'

print('=== Step 1: Import & Schema ===')
from app import app, db, User, ChatRecord, Order, RefundRequest

with app.app_context():
    cols = [c['name'] for c in db.inspect(db.engine).get_columns('chat_record')]
    assert 'rating' in cols and 'feedback' in cols, 'Column check failed!'
    print(f'OK - ChatRecord columns: {cols}')
    
    admin = User.query.filter_by(username='admin').first()
    user1 = User.query.filter_by(username='user1').first()
    assert admin and user1, 'Seeded users not found!'
    print(f'OK - Users: admin(#{admin.id}), user1(#{user1.id})')

print('\n=== Step 2: Route tests ===')
with app.test_client() as c:
    assert c.get('/login').status_code == 200
    assert c.get('/register').status_code == 200
    print('OK - Static routes')

print('\n=== Step 3: Login tests ===')
with app.test_client() as c:
    rv = c.post('/login', data={'username': 'user1', 'password': 'user123'}, follow_redirects=True)
    assert rv.status_code == 200
    assert '聊天' in rv.get_data(as_text=True) or 'chat' in rv.get_data(as_text=True).lower()
    print('OK - user1 login')
    c.get('/logout')
    
    rv = c.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert rv.status_code == 200
    print('OK - admin login')
    c.get('/logout')

print('\n=== Step 4: Chat & Feedback API ===')
with app.test_client() as c:
    c.post('/login', data={'username': 'user1', 'password': 'user123'})
    
    # Send chat message
    rv = c.post('/api/chat', json={'text': '你好'}, content_type='application/json')
    data = rv.get_json()
    assert rv.status_code == 200, f'Chat failed: {rv.status_code}'
    reply_id = data.get('record_id')
    assert reply_id, f'No record_id in response: {data}'
    print(f'OK - Chat reply, record_id={reply_id}, reply={data.get("reply","")[:40]}')
    
    # Test feedback (点赞) using the reply record_id
    rv = c.post('/api/feedback', json={'record_id': reply_id, 'action': 'like'}, content_type='application/json')
    assert rv.status_code == 200, f'Feedback like failed: {rv.status_code}, body: {rv.get_json()}'
    print('OK - Feedback (like)')
    
    # Test rating (5星) using same reply record_id
    rv = c.post('/api/rating', json={'record_id': reply_id, 'rating': 5, 'suggestion': '很好'}, content_type='application/json')
    assert rv.status_code == 200, f'Rating failed: {rv.status_code}, body: {rv.get_json()}'
    print('OK - Rating (5 stars)')
    
    # Verify independence
    with app.app_context():
        rec = db.session.get(ChatRecord, reply_id)
        if rec:
            assert rec.feedback == 1, f'feedback should be 1, got {rec.feedback}'
            assert rec.rating == 5, f'rating should be 5, got {rec.rating}'
            print(f'OK - feedback({rec.feedback}) and rating({rec.rating}) are INDEPENDENT ✓')
    
    c.get('/logout')

print('\n=== Step 5: Refund API ===')
with app.test_client() as c:
    c.post('/login', data={'username': 'user1', 'password': 'user123'})
    
    # Apply refund (correct path: /api/refund/apply)
    rv = c.post('/api/refund/apply', json={'order_id': 1, 'reason': '商品有质量问题'}, content_type='application/json')
    data = rv.get_json()
    assert rv.status_code == 200, f'Refund apply failed: {rv.status_code}, body: {data}'
    refund_id = data.get('refund_id')
    assert refund_id, f'No refund_id: {data}'
    print(f'OK - Refund applied, id={refund_id}')
    
    c.get('/logout')

print('\n=== Step 6: Admin Refund Update ===')
with app.test_client() as c:
    c.post('/login', data={'username': 'admin', 'password': 'admin123'})
    
    # Approve (correct path: /api/admin/refund/<rid>/update)
    rv = c.post('/api/admin/refund/1/update', json={'status': '已批准', 'admin_note': '已处理'}, content_type='application/json')
    data = rv.get_json()
    assert rv.status_code == 200, f'Approve failed: {rv.status_code}, body: {data}'
    print('OK - Refund approved')
    
    # Duplicate approve (should fail)
    rv = c.post('/api/admin/refund/1/update', json={'status': '已批准', 'admin_note': '重复'}, content_type='application/json')
    data = rv.get_json()
    assert rv.status_code == 400, f'Duplicate should fail: {rv.status_code}'
    assert '不能重复审批' in data.get('msg', ''), f'Wrong error msg: {data}'
    print('OK - Duplicate approve blocked ✓')
    
    c.get('/logout')

print('\n=== Step 7: Order Confirm API ===')
with app.test_client() as c:
    c.post('/login', data={'username': 'user1', 'password': 'user123'})
    
    # Confirm order (correct path: /api/order/confirm)
    rv = c.post('/api/order/confirm', json={'order_id': 1}, content_type='application/json')
    assert rv.status_code == 200, f'Confirm failed: {rv.status_code}, body: {rv.get_json()}'
    print('OK - Order confirmed')
    
    # Duplicate confirm (should fail - order is now 已送达)
    rv = c.post('/api/order/confirm', json={'order_id': 1}, content_type='application/json')
    data = rv.get_json()
    assert rv.status_code == 400, f'Duplicate confirm should fail: {rv.status_code}'
    assert '无需重复' in data.get('msg', ''), f'Wrong error: {data}'
    print('OK - Duplicate confirm blocked ✓')

print('\n=== ALL 7 TESTS PASSED ===')
print('Summary: Chat, Feedback vs Rating independence, Refund, Approve, Confirm - all working')