import pytest
from backend.app import create_app

@pytest.fixture
def client(tmp_path):
    app=create_app({'TESTING':True,'DATABASE':str(tmp_path/'test.sqlite3'),'SECRET_KEY':'test-only','SESSION_COOKIE_SECURE':False,'SETUP_TOKEN':''})
    return app.test_client()

def owner(client):
    csrf=client.get('/api/auth').json['csrf']
    r=client.post('/api/setup',json={'email':'owner@example.com','password':'a-long-test-password'},headers={'X-CSRF-Token':csrf})
    assert r.status_code==200
    return {'X-CSRF-Token':r.json['csrf']}

def test_login_csrf_owner_and_private_api(client):
    assert client.get('/api/state').status_code==401
    csrf=owner(client)
    assert client.post('/api/demo',json={'revision':0}).status_code==403
    assert client.post('/api/setup',json={},headers=csrf).status_code==409
    assert client.get('/api/state').status_code==200
    assert client.post('/api/logout',json={},headers=csrf).status_code==200
    assert client.get('/api/state').status_code==401

def test_optimistic_writes_reject_lost_updates(client):
    csrf=owner(client)
    state=client.get('/api/state').json['state']
    state['profile']['name']='My profile'
    assert client.put('/api/state',json={'state':state,'revision':0},headers=csrf).status_code==200
    assert client.put('/api/state',json={'state':state,'revision':0},headers=csrf).status_code==409
    assert client.get('/api/state').json['revision']==1

def test_demo_purchase_backup_ask_and_csv(client):
    csrf=owner(client)
    r=client.post('/api/demo',json={'revision':0},headers=csrf)
    assert r.status_code==200
    assert client.get('/api/state').json['state']['accounts']
    assert client.post('/api/decision',json={'name':'Shoes','price':5000,'account':'hdfc'},headers=csrf).status_code==200
    assert 'answer' in client.post('/api/ask',json={'question':'How much are my EMIs?'},headers=csrf).json
    assert client.get('/api/export').json['schemaVersion']==1
    assert 'attachment' in client.get('/api/transactions.csv').headers['Content-Disposition']
    assert client.post('/api/demo',json={'revision':1},headers=csrf).status_code==400

def test_negative_nan_and_bad_foreign_keys_rejected(client):
    csrf=owner(client)
    state=client.get('/api/state').json['state']
    state['profile']['monthlyIncome']=-1
    assert client.put('/api/state',json={'state':state,'revision':0},headers=csrf).status_code==400
    state['profile']['monthlyIncome']=100
    state['profile']['salaryAccount']='missing'
    assert client.put('/api/state',json={'state':state,'revision':0},headers=csrf).status_code==400

def test_csv_import_is_atomic_and_ids_deduplicate(client):
    csrf=owner(client)
    demo=client.post('/api/demo',json={'revision':0},headers=csrf).json
    d=demo['summary']['asOf']
    csv=f'id,date,name,type,category,amount,account\ntx1,{d},Lunch,expense,Food,250,hdfc\n'
    r=client.post('/api/import-csv',json={'csv':csv,'revision':1},headers=csrf)
    assert r.status_code==200
    assert len(r.json['state']['transactions'])==1
    r=client.post('/api/import-csv',json={'csv':csv,'revision':2},headers=csrf)
    assert r.status_code==200
    assert len(r.json['state']['transactions'])==1
    bad=csv+f'tx2,{d},Bad,expense,Food,-5,hdfc\n'
    assert client.post('/api/import-csv',json={'csv':bad,'revision':3},headers=csrf).status_code==400
    assert client.get('/api/state').json['revision']==3

def test_password_change_invalidates_other_sessions(client):
    csrf=owner(client)
    app=client.application
    other=app.test_client()
    token=other.get('/api/auth').json['csrf']
    r=other.post('/api/login',json={'email':'owner@example.com','password':'a-long-test-password'},headers={'X-CSRF-Token':token})
    assert r.status_code==200
    assert other.get('/api/state').status_code==200
    r=client.post('/api/password',json={'currentPassword':'a-long-test-password','newPassword':'another-long-test-password'},headers=csrf)
    assert r.status_code==200
    assert client.get('/api/state').status_code==200
    assert other.get('/api/state').status_code==401

def test_login_attempt_throttling(client):
    owner(client)
    other=client.application.test_client()
    token=other.get('/api/auth').json['csrf']
    for i in range(10):
        assert other.post('/api/login',json={'email':'owner@example.com','password':'wrong'},headers={'X-CSRF-Token':token}).status_code==401
    assert other.post('/api/login',json={'email':'owner@example.com','password':'wrong'},headers={'X-CSRF-Token':token}).status_code==429
