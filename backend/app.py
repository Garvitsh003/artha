"""Single-owner self-hosted API with SQLite, sessions and optimistic writes."""
import csv
import io
import json
import os
import secrets
import sqlite3
import time
from datetime import timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, session, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from .finance import validate, empty_state, demo_state, summary, decision, mid, today

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    data_dir = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
    data_dir.mkdir(parents=True, exist_ok=True)
    secret = os.environ.get('SECRET_KEY')
    production = os.environ.get('APP_ENV') == 'production'
    if not secret:
        if production and not test_config:
            raise RuntimeError('Set SECRET_KEY before starting in production.')
        keyfile = data_dir / 'session.key'
        try:
            fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = keyfile.read_text().strip()
    if production and not test_config and (len(secret) < 32 or len(os.environ.get('SETUP_TOKEN', '')) < 20):
        raise RuntimeError('Production requires SECRET_KEY (32+ characters) and SETUP_TOKEN (20+ characters).')
    app.config.update(SECRET_KEY=secret, DATABASE=str(data_dir / 'artha.sqlite3'),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024, SESSION_COOKIE_NAME='artha_session',
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '1' if production else '0') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(days=7), SETUP_TOKEN=os.environ.get('SETUP_TOKEN', ''))
    if os.environ.get('TRUSTED_HOSTS'):
        app.config['TRUSTED_HOSTS'] = os.environ['TRUSTED_HOSTS'].split(',')
    if test_config:
        app.config.update(test_config)
    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'], timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA journal_mode=WAL')
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db
    app.db = db
    with app.app_context():
        db().executescript('''
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY CHECK(id=1), email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL, session_version INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS documents (
              user_id INTEGER PRIMARY KEY REFERENCES users(id), revision INTEGER NOT NULL DEFAULT 0,
              body TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS login_attempts (
              key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL);
        ''')
        db().commit()
    @app.teardown_appcontext
    def close_db(error):
        conn = g.pop('db', None)
        if conn:
            conn.close()
    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code
    @app.errorhandler(ValueError)
    def validation_error(error):
        return jsonify(error=str(error)), 400
    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        app.logger.exception('Database operation failed')
        return jsonify(error='Unable to save or load data. Please retry.'), 503
    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response
    @app.before_request
    def csrf():
        if request.path.startswith('/api/') and request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            token = session.get('csrf')
            supplied = request.headers.get('X-CSRF-Token', '')
            if not token or not secrets.compare_digest(token, supplied):
                return jsonify(error='Session expired. Reload and try again.'), 403
    def signed_in(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            owner = db().execute('SELECT * FROM users WHERE id=1').fetchone()
            if not owner or session.get('uid') != 1 or session.get('sv') != owner['session_version']:
                return jsonify(error='Please sign in.'), 401
            return fn(*args, **kwargs)
        return wrapper
    def body():
        result = request.get_json(silent=True)
        if not isinstance(result, dict):
            raise ValueError('Expected a JSON object.')
        return result
    def state():
        row = db().execute('SELECT * FROM documents WHERE user_id=1').fetchone()
        return json.loads(row['body']), row['revision']
    def save(s, revision):
        validate(s)
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise ValueError('A valid revision is required.')
        with db():
            result = db().execute('UPDATE documents SET body=?, revision=revision+1, updated_at=CURRENT_TIMESTAMP WHERE user_id=1 AND revision=?',
                (json.dumps(s, separators=(',', ':'), allow_nan=False), revision))
            if result.rowcount != 1:
                return jsonify(error='Your data changed on another device. Reload before saving; your draft is still open.'), 409
        return jsonify(state=s, revision=revision + 1, summary=summary(s))
    def establish(owner):
        session.clear()
        session.update(uid=1, sv=owner['session_version'], csrf=secrets.token_urlsafe(32))
        session.permanent = True
        return jsonify(user={'email': owner['email']}, csrf=session['csrf'])
    @app.get('/api/auth')
    def auth_status():
        owner = db().execute('SELECT * FROM users WHERE id=1').fetchone()
        session.setdefault('csrf', secrets.token_urlsafe(32))
        logged_in = bool(owner and session.get('uid') == 1 and session.get('sv') == owner['session_version'])
        return jsonify(setupRequired=owner is None, setupTokenRequired=bool(app.config['SETUP_TOKEN']),
            user={'email': owner['email']} if logged_in else None, csrf=session['csrf'])
    @app.post('/api/setup')
    def setup():
        data = body()
        if db().execute('SELECT 1 FROM users').fetchone():
            return jsonify(error='The owner account is already configured.'), 409
        expected = app.config['SETUP_TOKEN']
        if expected and not secrets.compare_digest(expected, str(data.get('setupToken', ''))):
            return jsonify(error='Incorrect setup token.'), 403
        email = str(data.get('email', '')).strip().lower()
        password = data.get('password', '')
        if '@' not in email or len(email) > 254 or not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError('Use a valid email and a password with 12–256 characters.')
        try:
            with db():
                db().execute('INSERT INTO users(id,email,password_hash) VALUES(1,?,?)', (email, generate_password_hash(password)))
                db().execute('INSERT INTO documents(user_id,body) VALUES(1,?)', (json.dumps(empty_state()),))
        except sqlite3.IntegrityError:
            return jsonify(error='The owner account is already configured.'), 409
        owner = db().execute('SELECT * FROM users WHERE id=1').fetchone()
        return establish(owner)
    @app.post('/api/login')
    def login():
        data = body()
        email = str(data.get('email', '')).strip().lower()[:254]
        password = data.get('password', '')
        if not isinstance(password, str) or len(password) > 256:
            raise ValueError('Invalid credentials.')
        # Persistent, per-client throttling across processes. Do not trust forwarded IP headers.
        key = request.remote_addr or 'unknown'
        now = int(time.time())
        with db():
            db().execute('INSERT INTO login_attempts(key,attempts,window_start) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=CASE WHEN window_start < ? THEN 1 ELSE attempts+1 END, window_start=CASE WHEN window_start < ? THEN ? ELSE window_start END',
                (key, now, now-900, now-900, now))
        attempts = db().execute('SELECT attempts FROM login_attempts WHERE key=?', (key,)).fetchone()['attempts']
        if attempts > 10:
            return jsonify(error='Too many sign-in attempts. Try again in 15 minutes.'), 429
        owner = db().execute('SELECT * FROM users WHERE id=1').fetchone()
        if not owner or email != owner['email'] or not check_password_hash(owner['password_hash'], password):
            return jsonify(error='Incorrect email or password.'), 401
        with db():
            db().execute('DELETE FROM login_attempts WHERE key=?', (key,))
        return establish(owner)
    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)
    @app.post('/api/password')
    @signed_in
    def password():
        data = body()
        owner = db().execute('SELECT * FROM users WHERE id=1').fetchone()
        if not check_password_hash(owner['password_hash'], str(data.get('currentPassword', ''))):
            return jsonify(error='Current password is incorrect.'), 403
        new = data.get('newPassword', '')
        if not isinstance(new, str) or not 12 <= len(new) <= 256:
            raise ValueError('New password must have 12–256 characters.')
        with db():
            db().execute('UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=1', (generate_password_hash(new),))
        return establish(db().execute('SELECT * FROM users WHERE id=1').fetchone())
    @app.get('/api/state')
    @signed_in
    def get_state():
        s, rev = state()
        return jsonify(state=s, revision=rev, summary=summary(s))
    @app.put('/api/state')
    @signed_in
    def put_state():
        data = body()
        return save(data.get('state'), data.get('revision'))
    @app.post('/api/demo')
    @signed_in
    def demo():
        data = body()
        s, rev = state()
        if s['accounts'] or s['transactions']:
            raise ValueError('Demo data can only be loaded into an empty account.')
        return save(demo_state(), data.get('revision'))
    @app.post('/api/decision')
    @signed_in
    def purchase():
        s, rev = state()
        return jsonify(decision(s, body()))
    @app.post('/api/ask')
    @signed_in
    def ask():
        question = str(body().get('question', '')).strip().lower()
        if not question or len(question) > 400:
            raise ValueError('Enter a question under 400 characters.')
        s, _ = state()
        snap = summary(s)
        fmt = lambda n: f'₹{n:,.0f}'
        if any(word in question for word in ['spend', 'afford', 'weekend', 'available']):
            answer = f"Your current safe-to-spend estimate is {fmt(snap['safeToSpend'])}. You have {fmt(snap['bankBalance'])} in bank accounts, {fmt(snap['protected'])} protected, and an extra {fmt(s['profile']['cashBuffer'])} cash buffer. The estimate also reserves the lowest projected discretionary cash over the next 30 days."
        elif any(word in question for word in ['emi', 'loan']):
            answer = f"Your scheduled monthly EMI burden is {fmt(snap['monthlyEMI'])}, or {snap['emiRatio']}% of planned take-home income. Outstanding loan principal is {fmt(sum(e['remainingPrincipal'] for e in snap['emis']))}."
            if snap['emis']:
                nearest = min(snap['emis'], key=lambda e:e['endMonth'])
                answer += f" {nearest['name']} is scheduled to finish in {nearest['endMonth']}, freeing {fmt(nearest['amount'])} per month after its final instalment."
        elif any(word in question for word in ['pf', 'epf', 'retirement']):
            answer = f"Your manually recorded PF corpus totals {fmt(sum(a['value'] for a in s['assets'] if a['kind']=='PF'))}. It is included in net worth and excluded from spending decisions. EPS is excluded from EPF corpus projections."
        elif any(word in question for word in ['worth', 'wealth']):
            answer = f"Your recorded net worth is {fmt(snap['netWorth'])}: {fmt(snap['bankBalance'])} in banks + {fmt(snap['assetValue'])} in other assets − {fmt(snap['liabilities'])} in debt."
        elif any(word in question for word in ['expense', 'spent', 'spending']):
            answer = f"Recorded expenses this month total {fmt(snap['actualExpense'])}. Transfers are excluded. " + ', '.join(f'{k}: {fmt(v)}' for k,v in sorted(snap['categories'].items(), key=lambda x:-x[1]))
        elif any(word in question for word in ['due', 'upcoming', 'bill']):
            answer = '\n'.join(f"{e['name']}: {fmt(e['amount'])}, due {e['dueDate']} ({'overdue' if e['overdue'] else 'upcoming'})" for e in snap['upcoming'][:10]) or 'No unpaid scheduled bills in the next 30 days.'
        elif any(word in question for word in ['forecast', 'future', 'months', 'saving']):
            r = snap['forecast'][-1]
            answer = f"By {r['date']}, discretionary cash is estimated at {fmt(r['available'])}, with total bank balances of {fmt(r['bankBalance'])}. This assumes your planned salary and costs continue and no unscheduled purchases or transfers occur."
        elif any(word in question for word in ['buy', 'purchase', 'cash']):
            answer = 'Use Purchase planner to enter the price, payment account and cash/EMI terms. It checks your daily forecast, protected floors and fees, and shows the comparison.'
        else:
            answer = 'I can calculate safe spending, monthly EMIs, PF corpus, net worth, recorded expenses, upcoming bills and your forecast. For a purchase, use Purchase planner. Answers use explicit rules rather than an external AI service.'
        return jsonify(answer=answer)
    @app.get('/api/export')
    @signed_in
    def export():
        s, rev = state()
        response = jsonify(s)
        response.headers['Content-Disposition'] = f'attachment; filename=artha-backup-{today()}.json'
        return response
    @app.get('/api/transactions.csv')
    @signed_in
    def export_csv():
        s, _ = state()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(['id','date','name','type','category','amount','account','toAccount','ref','principalPaid'])
        for t in sorted(s['transactions'], key=lambda x: x['date']):
            # Prevent spreadsheet formula execution in user-provided text.
            writer.writerow([("'" + str(t.get(k, '')) if str(t.get(k, '')).startswith(('=','+','-','@')) else t.get(k, ''))
                for k in ['id','date','name','type','category','amount','account','toAccount','ref','principalPaid']])
        return out.getvalue(), 200, {'Content-Type':'text/csv', 'Content-Disposition':'attachment; filename=artha-transactions.csv'}
    @app.post('/api/import-csv')
    @signed_in
    def import_csv():
        data = body()
        content = data.get('csv')
        if not isinstance(content, str) or len(content) > 1_000_000:
            raise ValueError('CSV must be under 1 MB.')
        s, rev = state()
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
        if not {'date', 'name', 'type', 'category', 'amount', 'account'}.issubset(reader.fieldnames or []):
            raise ValueError('CSV needs date,name,type,category,amount,account columns. Use account IDs from Settings.')
        seen = {t['id'] for t in s['transactions']}
        count = 0
        for row in reader:
            id_ = row.get('id') or mid('tx')
            if id_ in seen:
                continue
            try:
                amount = float(row['amount'])
                principal = float(row.get('principalPaid') or 0)
            except (ValueError, KeyError):
                raise ValueError('CSV amount and principalPaid must be numbers.')
            s['transactions'].append({'id':id_, 'date':row['date'], 'name':row['name'].removeprefix("'"),
                'type':row['type'], 'category':row['category'].removeprefix("'"), 'amount':amount,
                'account':row['account'], 'toAccount':row.get('toAccount',''), 'ref':row.get('ref',''), 'principalPaid':principal})
            seen.add(id_)
            count += 1
            if count > 1000:
                raise ValueError('Import at most 1,000 transactions at a time.')
        return save(s, data.get('revision'))
    @app.get('/health')
    def health():
        return jsonify(status='ok')
    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path='index.html'):
        if path.startswith('api/'):
            return jsonify(error='Endpoint not found.'), 404
        web = ROOT / 'dist-web'
        if not (web / 'index.html').exists():
            return 'Frontend not built. Run npm run build:web first.', 503
        if (web / path).is_file():
            return send_from_directory(web, path)
        return send_from_directory(web, 'index.html')
    return app

app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5000')), debug=False)
