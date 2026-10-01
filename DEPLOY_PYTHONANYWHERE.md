# Deploy Artha with PythonAnywhere + Vercel

PythonAnywhere runs the Flask API and stores SQLite. Vercel serves the React interface and forwards `/api` requests to PythonAnywhere. You do not need Docker, EC2, a paid AI API or a database migration for this deployment.

## 1. Upload to PythonAnywhere

Upload `artha-finance.zip` into your home directory using PythonAnywhere's Files tab. Open a Bash console:

```bash
cd ~
unzip artha-finance.zip
cd ~/artha-finance
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Use a Python version available both in the console and the Web tab; 3.11+ is required. If you choose 3.12 in the Web tab, use `python3.12` for the virtualenv instead.

Do not re-extract a later archive over your `.env` or `data/` directory. The distributed archive excludes real financial records, passwords and server secrets. Keep the `dist-web/` folder: it also allows PythonAnywhere to serve the interface directly as a fallback.

## 2. Configure your server

Run in the same console, replacing the hostname with the exact address shown in PythonAnywhere's Web tab:

```bash
python deployment/configure_pythonanywhere.py --hostname YOURUSERNAME.pythonanywhere.com
```

EU accounts may use `YOURUSERNAME.eu.pythonanywhere.com`; use the hostname actually shown by your account. Pass a hostname without `https://` or any slash.

The script creates:

- A private `.env` with new SECRET_KEY and SETUP_TOKEN values, secure cookies, an absolute persistent data path and SQLite rollback-journal mode.
- A `vercel.json` that routes API requests to your PythonAnywhere address.

The script refuses to overwrite an existing `.env`. For an existing installation, retain SECRET_KEY and SETUP_TOKEN and set these fields manually in that file:

```dotenv
APP_ENV=production
COOKIE_SECURE=1
SQLITE_JOURNAL_MODE=DELETE
DATA_DIR=/home/YOURUSERNAME/artha-finance/data
TRUSTED_HOSTS=YOURUSERNAME.pythonanywhere.com
```

For this deployment, keep **SQLITE_JOURNAL_MODE=DELETE**. PythonAnywhere uses a network filesystem and its staff explicitly state that SQLite WAL is not supported. SQLite is available there, but it is not their recommended database for high-volume production workloads. This application is intended for one owner with light personal use. Export backups regularly.

Do not upload your local development database or session key unless you deliberately intend to migrate them. To carry existing finances across, export a JSON backup from the old app and restore it after signing into the new installation.

## 3. Create the PythonAnywhere web app

In **Web → Add a new web app**:

1. Select **Manual configuration**.
2. Select the same Python version used for `.venv`.
3. Set **Source code** and **Working directory** to `/home/YOURUSERNAME/artha-finance`.
4. Set **Virtualenv** to `/home/YOURUSERNAME/artha-finance/.venv`.
5. Open the WSGI configuration link. Replace its sample application code with the contents of `deployment/pythonanywhere_wsgi.py`.

The WSGI contents are:

```python
import sys
from pathlib import Path

project_home = Path.home() / 'artha-finance'
if str(project_home) not in sys.path:
    sys.path.insert(0, str(project_home))

from backend.app import app as application
```

This imports the app; it does not start a development server. The backend already loads `.env` from the project root before creating the Flask app.

Enable **Force HTTPS** in the Web tab, then click **Reload**. PythonAnywhere provides HTTPS for its own account subdomains. No custom domain or certificate purchase is needed.

Visit:

```text
https://YOURUSERNAME.pythonanywhere.com/health
https://YOURUSERNAME.pythonanywhere.com/api/auth
```

The first should show `{"status":"ok"}`. The second should return JSON with `setupRequired` and a CSRF token. If it fails, open the Web tab's error log. Common causes are a mismatched virtualenv version, incorrect project path, missing packages, a wrong TRUSTED_HOSTS hostname or a missing/short production secret.

Do not launch `python -m backend.app` or Gunicorn as a permanent Bash-console server. PythonAnywhere hosts this version through the Web tab and WSGI configuration.

## 4. Deploy the interface to Vercel

Download **only `vercel.json`** from PythonAnywhere back into your local extracted project folder, replacing the supplied placeholder file. It must sit beside `package.json`.

If you prefer to edit it locally, replace `YOURUSERNAME.pythonanywhere.com` in its destination with your exact PythonAnywhere hostname. Retain the `/api/` part of the destination.

Push the project to a private GitHub repository. The included `.gitignore` excludes `.env`, `data/`, `.venv/` and `node_modules/`. Confirm these are not tracked before pushing. Keep `vercel.json` tracked; it contains routing configuration, not secrets.

Import that repository in Vercel. Use:

| Setting | Value |
|---|---|
| Root directory | Folder containing `package.json` |
| Framework preset | Vite |
| Node.js version | 24.x |
| Install command | `npm install` |
| Build command | `npm run build:web` |
| Output directory | `dist-web` |

The supplied `vercel.json` sets the framework, install, build and output options. The explicit install command uses npm on Vercel; the original pnpm lockfile remains available for reproducible local builds. Do not select Next.js because it appears among the bundled dependencies.

You do **not** put SECRET_KEY, SETUP_TOKEN or your SQLite database on Vercel. They remain on PythonAnywhere.

After deployment, open:

```text
https://YOUR-VERCEL-PROJECT.vercel.app/api/auth
```

It should return the same shape of JSON as the direct PythonAnywhere endpoint. If it returns HTML, check the rewrite and backend status. If it returns 400, check the exact backend hostname in `TRUSTED_HOSTS` and the rewrite destination. If it returns 502, inspect the PythonAnywhere error log and reload its web app.

The frontend already calls relative `/api` URLs. The Vercel rewrite keeps API requests on the same browser origin; retain the existing session-cookie and CSRF protections. Do not change fetch to call PythonAnywhere directly or add permissive CORS. API responses are marked `no-store`, and the rewrite configuration disables external-response caching.

## 5. Create your login and verify persistence

Open the Vercel site. On the owner setup screen, enter your email, a strong password of at least 12 characters, and the SETUP_TOKEN from PythonAnywhere's private `.env` file. Read that file through the PythonAnywhere Files tab; keep the token private.

If you already created the owner account through the direct PythonAnywhere interface, use its existing login. Both interfaces use the same server-side financial records, although each domain has a separate browser session cookie.

Add one real account and transaction. Reload the page, sign out and back in, and then open it on a second device. Verify the record is still present. On iPhone, open the Vercel URL in Safari and use Share → Add to Home Screen.

If you are on a PythonAnywhere free account, renew the web app before the expiry date shown in its Web tab. Keep its data directory when deploying updates. Export JSON backups from Income & rules regularly.

## Provider references

- Flask deployment: https://help.pythonanywhere.com/pages/Flask
- SQLite support: https://help.pythonanywhere.com/pages/KindsOfDatabases
- WAL support clarification: https://www.pythonanywhere.com/forums/topic/36213/
- HTTPS: https://help.pythonanywhere.com/pages/HTTPSSetup
- Free account features: https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
- Vercel rewrites: https://vercel.com/docs/routing/rewrites

The deployment templates and local regression tests are included. They have not been deployed to your PythonAnywhere or Vercel accounts here.
