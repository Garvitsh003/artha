"""Run on PythonAnywhere after extraction. Generates local secrets and Vercel routing."""
import argparse
import json
import re
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--hostname', help='Exact web-app hostname shown in the PythonAnywhere Web tab.')
args = parser.parse_args()
host = args.hostname or (Path.home().name + '.pythonanywhere.com')
if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host) or '.' not in host:
    parser.error('Pass a hostname only, without https://, a port or a path.')
env_path = root / '.env'
if env_path.exists():
    raise SystemExit('An .env file already exists. Keep its existing secrets; update settings manually using DEPLOY_PYTHONANYWHERE.md.')
lines = [
    'APP_ENV=production',
    'COOKIE_SECURE=1',
    'SQLITE_JOURNAL_MODE=DELETE',
    'SECRET_KEY=' + secrets.token_hex(32),
    'SETUP_TOKEN=' + secrets.token_urlsafe(32),
    'DATA_DIR=' + str(root / 'data'),
    'TRUSTED_HOSTS=' + host,
]
with env_path.open('x') as f:
    f.write('\n'.join(lines) + '\n')
env_path.chmod(0o600)
config = {
    '$schema': 'https://openapi.vercel.sh/vercel.json',
    'framework': 'vite',
    'installCommand': 'npm install',
    'buildCommand': 'npm run build:web',
    'outputDirectory': 'dist-web',
    'rewrites': [{'source': '/api/:path*', 'destination': 'https://' + host + '/api/:path*'}],
    'headers': [{'source': '/api/:path*', 'headers': [
        {'key': 'Cache-Control', 'value': 'no-store'},
        {'key': 'x-vercel-enable-rewrite-caching', 'value': '0'},
    ]}],
}
(root / 'vercel.json').write_text(json.dumps(config, indent=2) + '\n')
print('Created private .env and vercel.json for https://' + host)
print('Copy only vercel.json back to your local source folder; keep .env on PythonAnywhere.')
print('After web-app reload, copy SETUP_TOKEN from the private .env file into the initial setup screen.')
