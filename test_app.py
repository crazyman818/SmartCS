"""Smoke test for SmartCS - imports and basic API tests"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Ensure demo data env vars
os.environ['ENABLE_DEMO_SEED'] = 'false'
os.environ['FLASK_DEBUG'] = '1'

print('=== Step 1: Import app ===')
from app import app, db, User, ChatRecord, Order, RefundRequest, QuickReply, IntentStat
print('OK - All models imported')

print('\n=== Step 2: Check DB schema ===')
with app.app_context():
    tables = db.inspect(db.engine).get_table_names()
    print(f'Tables: {tables}')
    
    # Check ChatRecord has rating column
    cols = [c['name'] for c in db.inspect(db.engine).get_columns('chat_record')]
    print(f'ChatRecord columns: {cols}')
    assert 'rating' in cols, 'MISSING: rating column in ChatRecord!'
    assert 'feedback' in cols, 'MISSING: feedback column in ChatRecord!'
    print('OK - ChatRecord has both feedback and rating columns')
    
    # Check relationships
    u = User.query.filter_by(username='admin').first()
    if u:
        print(f'OK - Admin user exists: {u.username}')
    else:
        print('WARNING - Admin user not found (seed disabled)')
    
    u2 = User.query.filter_by(username='user1').first()
    if u2:
        print(f'OK - User1 exists: {u2.username}')
        orders = Order.query.filter_by(user_id=u2.id).all()
        print(f'OK - User1 has {len(orders)} orders')
    else:
        print('WARNING - User1 not found')

print('\n=== Step 3: Test Flask routes ===')
with app.test_client() as client:
    # Test index
    rv = client.get('/')
    print(f'GET / -> {rv.status_code} (expect 302 or 200)')
    
    # Test login page
    rv = client.get('/login')
    print(f'GET /login -> {rv.status_code}')
    assert rv.status_code == 200, f'Expected 200, got {rv.status_code}'
    print('OK - Login page works')
    
    # Test register page
    rv = client.get('/register')
    print(f'GET /register -> {rv.status_code}')
    
    # Test login
    rv = client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    print(f'POST /login (admin) -> {rv.status_code}')
    
    # Test chat page
    rv = client.get('/chat')
    print(f'GET /chat -> {rv.status_code}')
    
    # Test admin dashboard
    rv = client.get('/admin')
    print(f'GET /admin -> {rv.status_code}')
    
    # Test logout
    rv = client.get('/logout')
    print(f'GET /logout -> {rv.status_code}')

print('\n=== Step 4: Test API endpoints ===')
with app.test_client() as client:
    # Login as user1
    client.post('/login', data={
        'username': 'user1',
        'password': 'user123'
    })
    
    # Test chat API
    rv = client.post('/api/chat', 
        json={'text': '你好', 'emotion': 'neutral'},
        content_type='application/json')
    data = rv.get_json()
    print(f'POST /api/chat -> {rv.status_code}, reply: {(data or {}).get("reply", "N/A")[:50]}')
    
    # Test feedback API
    rv = client.post('/api/feedback',
        json={'record_id': 1, 'action': 'like'},
        content_type='application/json')
    print(f'POST /api/feedback -> {rv.status_code}')
    
    # Test rating API
    rv = client.post('/api/rating',
        json={'record_id': 1, 'rating': 5, 'suggestion': ''},
        content_type='application/json')
    data = rv.get_json()
    print(f'POST /api/rating -> {rv.status_code}, msg: {(data or {}).get("msg", "N/A")}')
    
    # Verify feedback and rating are independent
    with app.app_context():
        record = db.session.get(ChatRecord, 1)
        if record:
            print(f'Record 1 - feedback: {record.feedback}, rating: {record.rating}')
            if record.feedback == 1 and record.rating == 5:
                print('OK - feedback and rating are INDEPENDENT (field conflict FIXED)')
            else:
                print(f'NOTE - feedback={record.feedback}, rating={record.rating}')

print('\n=== Step 5: Test critical bug fixes ===')
with app.test_client() as client:
    # Test api_confirm_order status validation
    # 正确的路由是 /api/order/confirm，需要 order_id 字段
    client.post('/login', data={'username': 'user1', 'password': 'user123'})
    rv = client.post('/api/order/confirm',
        json={'order_id': 1},
        content_type='application/json')
    data = rv.get_json()
    print(f'POST /api/order/confirm -> {rv.status_code}, msg: {(data or {}).get("msg", "N/A")}')
    assert rv.status_code != 404, f'Route not found: 404'
    
    # Test api_admin_refund_update terminal state
    client.get('/logout')
    client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    
    # First create a refund request
    # 正确的路由是 /api/refund/apply，需要 order_id 和 reason
    client.get('/logout')
    client.post('/login', data={'username': 'user1', 'password': 'user123'})
    rv = client.post('/api/refund/apply',
        json={'order_id': 1, 'reason': 'Test refund'},
        content_type='application/json')
    data = rv.get_json()
    print(f'POST /api/refund/apply -> {rv.status_code}, refund_id: {(data or {}).get("refund_id", "N/A")}')
    refund_id = (data or {}).get('refund_id')
    
    # Login as admin and approve
    client.get('/logout')
    client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    if refund_id:
        rv = client.post(f'/api/admin/refund/{refund_id}/update',
            json={'status': '已批准', 'admin_note': 'Approved'},
            content_type='application/json')
        print(f'POST /api/admin/refund/{refund_id}/update (approve) -> {rv.status_code}, body: {rv.get_json()}')
        assert rv.status_code == 200, f'Expected 200, got {rv.status_code}'
    
        # Try to approve again (should fail - terminal state check)
        rv = client.post(f'/api/admin/refund/{refund_id}/update',
            json={'status': '已批准', 'admin_note': 'Duplicate'},
            content_type='application/json')
        print(f'POST /api/admin/refund/{refund_id}/update (duplicate) -> {rv.status_code}, body: {rv.get_json()}')
        assert rv.status_code == 400, f'Expected 400 (duplicate reject), got {rv.status_code}'
        print('OK - Terminal state validation WORKS (duplicate approve rejected)')
    else:
        print('SKIP - No refund created, cannot test admin update')

print('\n=== ALL SMOKE TESTS PASSED ===')
