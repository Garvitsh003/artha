"""Owner recovery: run locally on the host or inside the Docker app container."""
from getpass import getpass
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app import app
from werkzeug.security import generate_password_hash
password=getpass('New password (12+ characters): ')
if not 12 <= len(password) <= 256:
    raise SystemExit('Password must be 12–256 characters.')
with app.app_context():
    with app.db():
        cursor=app.db().execute('UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=1',(generate_password_hash(password),))
        if cursor.rowcount != 1:
            raise SystemExit('Owner account not configured.')
print('Password reset. Existing sessions signed out.')
