# Artha — Personal Finance

A complete self-hosted personal-finance web app for INR. React + TypeScript frontend, Flask API, SQLite persistence. Responsive on iPhone, desktop and tablet. The same hosted server keeps your records consistent across devices. No paid API key is needed.

## PythonAnywhere + Vercel

See **DEPLOY_PYTHONANYWHERE.md** for the complete two-host setup. It includes WSGI, automatic production secret generation, persistent SQLite settings and Vercel API routing.

## Start on your Mac (no Node required)

The archive includes the compiled frontend and all source code. Extract into a **new `artha-finance` folder**.

```bash
cd artha-finance
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m backend.app
```

Open **http://127.0.0.1:5000**. Create the owner account with an email and a password of at least 12 characters. Start with your own accounts or explicitly choose **Try sample finances**. Sample numbers are illustrative, not your actual finances.

Windows: activate with `.venv\Scripts\activate` rather than `source`. Use `py -3` if `python3` is unavailable. Python 3.11+ is required. Keep the server running while using the app. Stop with Ctrl+C.

## Features

- Owner setup, password login, password change and sign-out.
- Multiple bank accounts with purpose, opening balance/date, minimum balance, protected reserve and spendable/protected setting.
- Add, edit, delete and filter income, expenses and transfers. Actual transactions update bank balances.
- Monthly recurring bills and investment commitments; record salary and payments without posting them twice.
- EMI amount, payment account, due date, annual rate, starting principal, next unpaid month, scheduled instalments and final month.
- Principal repayments are separate from interest. Unpaid previous instalments remain overdue.
- PF, FD, mutual fund, stock and other asset valuations, plus card and other debt. Net worth subtracts liabilities.
- Employee EPF, employer EPF and employer EPS fields. Editable return assumption with 1/5/10-year corpus estimates.
- Purchase planner: pay in full or EMI, down payment, fees, rate and term. It checks daily cash and account funding, explains its decision and compares scenarios.
- Wishlist, monthly spending breakdown, up to 24 calendar months of forecasts, and a rule-based question assistant.
- JSON backup/restore, CSV transaction import/export, revision conflict checks for simultaneous devices.
- Installable web manifest and iPhone Home Screen support. Financial APIs are never cached for offline use.
- Docker files and Caddy HTTPS hosting configuration.

## Set up your real finances

1. Add every bank account. Use its balance **on the opening date before transactions you enter for that date**. Do not enter both today's balance and historical spending already included in it.
2. Turn off **Include in spendable cash** for emergency savings, IPO capital and any account you want fully protected.
3. Set the minimum balance and **protected reserve** on spendable accounts. The reserve is for protected goals/emergencies. Do not duplicate scheduled bill/EMI budgets here. Minimum and reserve overlap; the larger is protected.
4. In **Income & rules**, enter monthly **take-home** salary, salary day/account, and a variable-spending budget/account. Exclude costs already entered as bills or EMIs. Set an additional cash buffer and a purchase comfort buffer.
5. Add bills, SIPs and EMIs. Use the **first unpaid month**, not the loan's original start month. Instalment count covers the schedule starting then. Enter statement principal outstanding at the beginning of this schedule.
6. Record each actual payment. For an EMI, enter the principal component from your lender statement. Zero leaves principal unchanged until you update the payment. Paid schedule entries disappear from upcoming costs.
7. Record received salary using **Record salary received** in Bills & EMIs. This links it to the month and prevents the forecast from adding the same salary again. A generic income transaction does not cancel a scheduled salary assumption.
8. Add PF and investments as assets. For employer PF, split EPF and EPS using your passbook. Employee PF has already reduced take-home pay, so do not deduct it again in spending rules.
9. Credit-card balances and investment valuations are manual. Also add the actual upcoming card payment as a bill. After paying or making a SIP, update the liability/asset valuation separately. Avoid counting an FD both in a bank opening balance and as a separate asset.
10. If one account needs EMI funding, record the actual transfer. Forecasts do not invent transfers between your accounts.

## How calculations work

Money arithmetic uses **integer paise**, not accumulated binary floating-point amounts. Enter up to two decimal places.

```
Account balance = opening balance + income − expenses − outgoing transfers + incoming transfers
Protected floor = max(minimum balance, protected reserve)
Available cash = sum(balance − floor for spendable accounts) − additional cash buffer
Net worth = all bank balances + manually valued assets − loan principal − other liabilities
```

**Safe to spend** is the smaller of available cash today and the lowest projected aggregate discretionary cash through the next 30 days, clamped at zero. It includes unpaid scheduled obligations and the remaining variable budget. The monthly variable budget is reduced by actual non-scheduled expenses and distributed over the remaining days. Future salary is added on its due date only when its salary reference has not been recorded. FDs, investments, PF and protected accounts are excluded from purchase funding.

A purchase receives **BUY COMFORTABLY** only when the chosen account can cover its upfront cost, the daily projection remains above the comfort buffer, and no payment account falls below its protected floor. **WAIT** or **FINANCIALLY RISKY** explain projected cash shortages and funding problems. Aggregate safe-to-spend does not guarantee a particular account is funded.

Cash purchases are checked for 90 days. EMI purchases are checked for at least 90 days and through the selected term plus a margin. A possible later purchase date, when found, uses a future 30-day window; it is an estimate, not a promise. Comparison charts show month-end discretionary cash within the displayed horizon. A longer EMI can leave an unpaid balance after a short comparison horizon.

The EMI quote uses a standard reducing-balance formula; 0% means principal divided by term. All fees/taxes must be entered separately. Last-instalment rounding, retailer discounts, lender-specific GST treatment and prepayment costs are not inferred. Recorded loan liabilities use actual statement principal and entered principal repayments, rather than assuming all EMI payments reduce principal.

PF projections approximate monthly growth using an effective monthly rate and contribution at month end. Only employee EPF + employer EPF build the corpus. Employer EPS is not added. These projections are **planning assumptions**, not passbook calculations, guaranteed returns or current statutory rates. Asset valuations do not auto-update in the forecast.

The question assistant uses explicit calculation rules. It is not a connected LLM, a bank feed or a stock/IPO recommendation system. It can answer safe spending, EMI load, PF, net worth, recorded expense, due bills and cash forecasts. Purchase checks use the dedicated planner.

## Edit the frontend

Requires Node **24 LTS** and the pinned pnpm version. The existing lockfile is included.

```bash
corepack enable
corepack prepare pnpm@11.25.0 --activate
pnpm install --frozen-lockfile
pnpm run dev:web
```

Keep `python3 -m backend.app` running in another terminal. Open **http://localhost:5173**. Vite forwards `/api` to the Python server. After editing:

```bash
pnpm run typecheck:web
pnpm run build:web
```

The Python server serves `dist-web` at port 5000. If Corepack is not installed, install it first with `npm install -g corepack`. `npm install` can also install the declared dependencies, but pnpm is the reproducible path with the included lockfile.

## Docker locally

```bash
docker compose -f compose.local.yaml up --build -d
```

Open **http://127.0.0.1:5000**. This local configuration binds only to loopback and uses a named volume. It does not need a domain or manual secret generation. To stop:

```bash
docker compose -f compose.local.yaml down
```

Do not add `-v` unless you intend to delete stored data.

## Host on a VPS / EC2 with HTTPS

Use a server with Docker and the Compose plugin, a domain whose DNS points to it, and inbound TCP 80/443. Copy the extracted source directory to that server. Generate a fresh `.env` there:

```bash
python3 scripts/generate-secrets.py > .env
```

Edit `.env` and set `DOMAIN=finance.yourdomain.com` to your actual domain. Keep its generated secrets private. Then:

```bash
docker compose up --build -d
docker compose logs -f artha
```

Caddy obtains an HTTPS certificate and forwards traffic to Gunicorn. Visit `https://finance.yourdomain.com`. The initial setup screen requires the `SETUP_TOKEN` from your server's `.env`; after owner creation, additional registration is disabled. Cookies are marked Secure in this configuration. Set up the owner promptly. The app port is not exposed publicly by this Compose file.

On iPhone, open the HTTPS URL in Safari, tap Share, and choose **Add to Home Screen**. It remains an online app. Viewing it on another device uses the same owner login and the same server database.

A non-Docker host can run `gunicorn --bind 127.0.0.1:5000 --workers 2 --threads 2 backend.app:app` behind an HTTPS reverse proxy. Set `APP_ENV=production`, `COOKIE_SECURE=1`, `SECRET_KEY`, `SETUP_TOKEN`, `DATA_DIR` on persistent disk, and `TRUSTED_HOSTS` to your domain. The development server is for local use. Flask deployment guidance: https://flask.palletsprojects.com/en/stable/deploying/.

SQLite needs a persistent volume. An ephemeral hosting filesystem loses records when recreated. This package targets one personal server; it is not a horizontally scaled SaaS service.

## Backups and account recovery

Use **Income & rules → Download JSON backup** regularly. The JSON contains financial records, not passwords or session keys. Restore requires authentication and explicit replacement confirmation. CSV import is atomic, validates all rows and skips existing transaction IDs. Re-importing CSV without IDs can create duplicates.

The server data directory also contains SQLite and, in local mode, a generated session key. Database files are not encrypted at rest by this app; use your host's disk/volume protection. API responses use `Cache-Control: no-store`, write requests require CSRF tokens, passwords are hashed, and financial data stays behind owner authentication. There is no recovery email service.

For a forgotten password, run on the host:

```bash
python3 scripts/reset-password.py
```

Or with production Docker:

```bash
docker compose exec artha python scripts/reset-password.py
```

This prompts privately and invalidates old sessions. Keep the existing secret and database volume when updating the app.

## CSV format

Account IDs are available in **Income & rules → Account IDs for CSV imports**.

```csv
id,date,name,type,category,amount,account,toAccount,ref,principalPaid
lunch-001,2026-10-01,Lunch,expense,Food,250,hdfc,,,0
transfer-001,2026-10-01,EMI funding,transfer,Transfer,15000,hdfc,sbi,,0
```

Use your actual account IDs and valid dates on/after their opening date. Actual transactions cannot be future-dated. Optional salary reference: `salary:YYYY-MM`. Scheduled payment references are generated by the app. Amounts are positive. Import up to 1,000 new rows per upload. Exported user text is escaped against spreadsheet formula execution.

## Validation

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests -q
pnpm run typecheck:web
pnpm run build:web
```

Tests cover reserves, transfers, overdue payments, variable budgets, salary deduplication, short months, EMI end dates, principal repayments, PF/EPS separation, financing fees, account deficits, money precision, private APIs, CSRF, conflicting device writes, CSV atomicity, password session invalidation and login throttling.

## Source map

- `web/App.tsx`: responsive screens, record forms and interactions.
- `web/types.ts`: financial types.
- `app/globals.css`: theme and responsive layout.
- `backend/app.py`: authentication, persistence, import/export and APIs.
- `backend/finance.py`: validation, cash-flow, purchase decisions and PF projections.
- `components/ui/`, `hooks/`, `lib/utils.ts`: reusable accessible interface primitives.
- `public/`: manifest, icons and service worker.
- `dist-web/`: compiled frontend so Python can run immediately.
- `tests/`: financial and API regression tests.
- `Dockerfile`, `compose.yaml`, `compose.local.yaml`, `Caddyfile`: deployment.

Manual/CSV entry is the first version. No bank connection, automated PF passbook fetching, market-price feed, offline financial editing, push notifications or external AI integration is included.
