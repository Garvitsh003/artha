"""Deterministic INR planning. Money is calculated in integer paise.
PF, investments, collateral and account reserves never fund purchases.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import copy
import math
import re
import uuid

MAX_MONEY = 1_000_000_000

def p(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def ru(value):
    return round(value / 100, 2)

def today():
    # India is the product's financial calendar, independent of server timezone.
    from datetime import datetime, timezone
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()

def month(d):
    return d.strftime('%Y-%m')

def add_month(m, n):
    y, mo = map(int, m.split('-'))
    z = y * 12 + mo - 1 + n
    return f'{z // 12:04d}-{z % 12 + 1:02d}'

def due(m, day):
    y, mo = map(int, m.split('-'))
    return date(y, mo, min(day, monthrange(y, mo)[1]))

def mid(prefix):
    return prefix + '_' + uuid.uuid4().hex[:12]

def empty_state():
    t = today()
    return {'schemaVersion': 1, 'profile': {'name': 'My finances', 'monthlyIncome': 0,
        'salaryDay': 1, 'salaryAccount': '', 'variableBudget': 0,
        'variableAccount': '', 'cashBuffer': 0, 'comfortBuffer': 0,
        'forecastMonths': 12}, 'accounts': [], 'transactions': [], 'bills': [],
        'emis': [], 'assets': [], 'wishlist': []}

def text(v, label, maxlen=120, required=True):
    if not isinstance(v, str) or len(v.strip()) > maxlen or (required and not v.strip()):
        raise ValueError(f'{label} must contain 1–{maxlen} characters.' if required else f'Invalid {label}.')
    return v.strip()

def number(v, label, low=0, high=MAX_MONEY, integer=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high:
        raise ValueError(f'{label} must be between {low} and {high}.')
    if integer and int(v) != v:
        raise ValueError(f'{label} must be a whole number.')
    if not integer and p(v) / 100 != v:
        raise ValueError(f'{label} supports up to two decimal places.')
    return int(v) if integer else v

def day(v, label='Day'):
    return number(v, label, 1, 31, True)

def valid_date(v):
    try:
        if not isinstance(v, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
            raise ValueError()
        return date.fromisoformat(v)
    except (ValueError, TypeError):
        raise ValueError('Use a valid YYYY-MM-DD date.')

def valid_month(v):
    if not isinstance(v, str):
        raise ValueError('Use a valid YYYY-MM month.')
    valid_date(v + '-01')
    if len(v) != 7:
        raise ValueError('Use a valid YYYY-MM month.')
    return v

def choice(v, values, label):
    if v not in values:
        raise ValueError(f'Invalid {label}.')
    return v

def validate(s):
    if not isinstance(s, dict) or s.get('schemaVersion') != 1:
        raise ValueError('Unsupported backup format.')
    required = ['profile', 'accounts', 'transactions', 'bills', 'emis', 'assets', 'wishlist']
    if any(k not in s for k in required):
        raise ValueError('Incomplete financial data.')
    if not isinstance(s['profile'], dict):
        raise ValueError('Invalid profile data.')
    for collection in required[1:]:
        if not isinstance(s[collection], list) or len(s[collection]) > (10000 if collection == 'transactions' else 500):
            raise ValueError(f'Too many or invalid {collection}.')
        ids = set()
        for item in s[collection]:
            if not isinstance(item, dict):
                raise ValueError('Invalid record.')
            i = text(item.get('id'), 'Record ID', 80)
            if i in ids:
                raise ValueError('Duplicate record ID.')
            ids.add(i)
    accounts = {a['id']: a for a in s['accounts']}
    def account(i, optional=False):
        if not isinstance(i, str):
            raise ValueError('Choose an existing account.')
        if i == '' and optional:
            return
        if i not in accounts:
            raise ValueError('Choose an existing account.')
    for a in s['accounts']:
        text(a.get('name'), 'Account name')
        text(a.get('bank', ''), 'Bank', required=False)
        text(a.get('purpose', ''), 'Purpose', 300, required=False)
        number(a.get('openingBalance'), 'Opening balance')
        number(a.get('reserve'), 'Account reserve')
        number(a.get('minimum'), 'Minimum balance')
        if not isinstance(a.get('spendable'), bool):
            raise ValueError('Choose whether this account is spendable.')
        if valid_date(a.get('openingDate')) > today():
            raise ValueError('Opening date cannot be in the future.')
    pr = s['profile']
    text(pr.get('name'), 'Name')
    for k in ['monthlyIncome', 'variableBudget', 'cashBuffer', 'comfortBuffer']:
        number(pr.get(k), k)
    day(pr.get('salaryDay'), 'Salary day')
    account(pr.get('salaryAccount'), pr.get('monthlyIncome') == 0)
    account(pr.get('variableAccount'), pr.get('variableBudget') == 0)
    number(pr.get('forecastMonths'), 'Forecast months', 1, 24, True)
    for b in s['bills']:
        text(b.get('name'), 'Bill name')
        text(b.get('category'), 'Category')
        number(b.get('amount'), 'Bill amount', .01)
        day(b.get('dueDay'))
        valid_month(b.get('startMonth'))
        if b['startMonth'] < add_month(month(today()), -120):
            raise ValueError('Start the bill schedule within the last ten years; enter older debt separately.')
        if b.get('endMonth'):
            valid_month(b['endMonth'])
            if b['endMonth'] < b['startMonth']:
                raise ValueError('End month must follow start month.')
        account(b.get('account'))
    for e in s['emis']:
        text(e.get('name'), 'EMI name')
        number(e.get('amount'), 'EMI amount', .01)
        number(e.get('principalOutstanding'), 'Outstanding principal')
        number(e.get('annualRate'), 'Annual interest rate', 0, 100)
        number(e.get('months'), 'Remaining scheduled instalments', 1, 480, True)
        day(e.get('dueDay'))
        valid_month(e.get('startMonth'))
        if e['startMonth'] < add_month(month(today()), -120):
            raise ValueError('Start the unpaid EMI schedule within the last ten years.')
        account(e.get('account'))
    refs = set()
    emap = {e['id']: e for e in s['emis']}
    bmap = {b['id']: b for b in s['bills']}
    for t in s['transactions']:
        kind = choice(t.get('type'), ['expense', 'income', 'transfer'], 'transaction type')
        text(t.get('name'), 'Description')
        text(t.get('category'), 'Category')
        number(t.get('amount'), 'Transaction amount', .01)
        d = valid_date(t.get('date'))
        if d > today():
            raise ValueError('Record actual transactions only; plan future costs as bills or EMIs.')
        account(t.get('account'))
        if d < valid_date(accounts[t['account']]['openingDate']):
            raise ValueError('Transaction predates this account’s opening balance.')
        if kind == 'transfer':
            account(t.get('toAccount'))
            if t['toAccount'] == t['account']:
                raise ValueError('Transfer accounts must differ.')
            if d < valid_date(accounts[t['toAccount']]['openingDate']):
                raise ValueError('Transfer predates the destination opening balance.')
        number(t.get('principalPaid', 0), 'Principal paid', 0, t['amount'])
        ref = t.get('ref', '')
        if ref:
            if ref in refs:
                raise ValueError('This scheduled payment is already recorded.')
            refs.add(ref)
            parts = ref.split(':')
            if len(parts) == 2 and parts[0] == 'salary':
                valid_month(parts[1])
                if kind != 'income' or t.get('principalPaid', 0):
                    raise ValueError('Salary payments must be income.')
            elif len(parts) == 3 and parts[0] in ['bill', 'emi']:
                valid_month(parts[2])
                record = (bmap if parts[0] == 'bill' else emap).get(parts[1])
                if not record or kind != 'expense':
                    raise ValueError('Scheduled payment does not match its account or record.')
                if parts[2] < record['startMonth']:
                    raise ValueError('Scheduled payment predates its schedule.')
                end = record.get('endMonth') if parts[0] == 'bill' else add_month(record['startMonth'], record['months'] - 1)
                if end and parts[2] > end:
                    raise ValueError('Scheduled payment follows its schedule.')
                if parts[0] != 'emi' and t.get('principalPaid', 0):
                    raise ValueError('Only EMI payments can reduce loan principal.')
            else:
                raise ValueError('Invalid scheduled payment reference.')
        elif t.get('principalPaid', 0):
            raise ValueError('Link principal repayments to an EMI.')
    for e in s['emis']:
        paid = sum(p(t.get('principalPaid', 0)) for t in s['transactions'] if t.get('ref', '').startswith('emi:' + e['id'] + ':'))
        if paid > p(e['principalOutstanding']):
            raise ValueError('Principal repayments exceed the starting outstanding principal.')
    for a in s['assets']:
        text(a.get('name'), 'Asset name')
        choice(a.get('kind'), ['PF', 'FD', 'Mutual fund', 'Stocks', 'Other asset', 'Credit card', 'Other debt'], 'asset type')
        number(a.get('value'), 'Current value / outstanding debt')
        for k in ['employee', 'employerEPF', 'employerEPS']:
            number(a.get(k, 0), k)
        number(a.get('annualRate', 0), 'Assumed annual return', 0, 50)
        valid_date(a.get('asOf'))
        if valid_date(a['asOf']) > today():
            raise ValueError('Asset valuation date cannot be in the future.')
    for w in s['wishlist']:
        text(w.get('name'), 'Wishlist item')
        number(w.get('price'), 'Purchase price', .01)
        text(w.get('note', ''), 'Note', 500, False)
    return s

def balances(s):
    result = {a['id']: p(a['openingBalance']) for a in s['accounts']}
    for t in s['transactions']:
        v = p(t['amount'])
        result[t['account']] += v if t['type'] == 'income' else -v
        if t['type'] == 'transfer':
            result[t['toAccount']] += v
    return result

def floor(a):
    # Minimum balance and virtual reserves overlap: protect the larger, not both.
    return max(p(a['minimum']), p(a['reserve']))

def free(s, bs):
    # Negative balances/floor breaches are retained, never clamped per account.
    return sum(bs[a['id']] - floor(a) for a in s['accounts'] if a['spendable']) - p(s['profile']['cashBuffer'])

def loan_left(s, e):
    paid = sum(p(t.get('principalPaid', 0)) for t in s['transactions'] if t.get('ref', '').startswith('emi:' + e['id'] + ':'))
    return p(e['principalOutstanding']) - paid

def events(s, start, end):
    paid = {t.get('ref') for t in s['transactions'] if t.get('ref')}
    result = []
    # Past unpaid schedule entries remain overdue and reserve cash immediately.
    for kind, records in [('bill', s['bills']), ('emi', s['emis'])]:
        for item in records:
            last = item.get('endMonth') if kind == 'bill' else add_month(item['startMonth'], item['months'] - 1)
            m = item['startMonth']
            count = 0
            while m <= month(end) and (not last or m <= last) and count < 600:
                ref = f'{kind}:{item["id"]}:{m}'
                d = due(m, item['dueDay'])
                if d <= end and ref not in paid:
                    result.append({'date': max(d, start).isoformat(), 'dueDate': d.isoformat(), 'name': item['name'],
                        'kind': kind, 'amount': item['amount'], 'account': item['account'], 'ref': ref, 'overdue': d < start})
                m = add_month(m, 1)
                count += 1
    return sorted(result, key=lambda x: (x['date'], x['dueDate'], x['name']))

def forecast(s, days=365, purchase=0, pay_account='', new_emi=0, emi_months=0, upfront=0, at=None):
    now = at or today()
    end = now + timedelta(days=days)
    bs = balances(s)
    if pay_account:
        bs[pay_account] -= purchase + upfront
    elif purchase or upfront:
        raise ValueError('Choose a payment account.')
    bydate = {}
    for ev in events(s, now, end):
        bydate.setdefault(ev['date'], []).append(ev)
    paid = {t.get('ref') for t in s['transactions']}
    pr = s['profile']
    rows = []
    variable_spent = sum(p(t['amount']) for t in s['transactions'] if t['type'] == 'expense' and not t.get('ref') and t['date'].startswith(month(now)))
    budgets = {}
    for offset in range(days + 1):
        d = now + timedelta(days=offset)
        key = month(d)
        income = costs = 0
        sd = due(key, pr['salaryDay'])
        # A salary due today is an assumption until its actual ledger entry exists.
        if d == sd and 'salary:' + key not in paid and pr['salaryAccount']:
            income = p(pr['monthlyIncome'])
            bs[pr['salaryAccount']] += income
        for ev in bydate.get(d.isoformat(), []):
            amt = p(ev['amount'])
            bs[ev['account']] -= amt
            costs += amt
        if new_emi and offset > 0 and d == due(key, now.day):
            months_since = (d.year - now.year) * 12 + d.month - now.month
            if 1 <= months_since <= emi_months:
                bs[pay_account] -= new_emi
                costs += new_emi
        if key not in budgets:
            remaining = max(0, p(pr['variableBudget']) - variable_spent) if key == month(now) else p(pr['variableBudget'])
            remaining_days = monthrange(d.year, d.month)[1] - d.day + 1
            budgets[key] = [remaining, remaining_days]
        if pr['variableAccount']:
            rem, count = budgets[key]
            v = (rem + count - 1) // count
            budgets[key] = [rem - v, count - 1]
            bs[pr['variableAccount']] -= v
            costs += v
        breaches = [{'account': a['name'], 'shortfall': ru(max(0, floor(a) - bs[a['id']]))}
                    for a in s['accounts'] if bs[a['id']] < floor(a)]
        rows.append({'date': d.isoformat(), 'bankBalance': ru(sum(bs.values())), 'available': ru(free(s, bs)),
            'income': ru(income), 'outflow': ru(costs), 'breaches': breaches,
            'accountBalances': {k: ru(v) for k, v in bs.items()}})
    return rows

def safe_amount(s, at=None):
    rows = forecast(s, 30, at=at)
    current = free(s, balances(s))
    return min(current, min(p(row['available']) for row in rows)), rows

def summary(s):
    now = today()
    bs = balances(s)
    bank = sum(bs.values())
    protected = sum(bs[a['id']] if not a['spendable'] else min(max(0, bs[a['id']]), floor(a)) for a in s['accounts'])
    assets = sum(p(a['value']) for a in s['assets'] if a['kind'] not in ['Credit card', 'Other debt'])
    debt = sum(p(a['value']) for a in s['assets'] if a['kind'] in ['Credit card', 'Other debt']) + sum(loan_left(s, e) for e in s['emis'])
    emi_monthly = sum(p(e['amount']) for e in s['emis'] if e['startMonth'] <= month(now) <= add_month(e['startMonth'], e['months'] - 1))
    bill_monthly = sum(p(b['amount']) for b in s['bills'] if b['startMonth'] <= month(now) and (not b.get('endMonth') or b['endMonth'] >= month(now)))
    actual = [t for t in s['transactions'] if t['date'].startswith(month(now))]
    expenses = sum(p(t['amount']) for t in actual if t['type'] == 'expense')
    income = sum(p(t['amount']) for t in actual if t['type'] == 'income')
    cats = {}
    for t in actual:
        if t['type'] == 'expense':
            cats[t['category']] = cats.get(t['category'], 0) + p(t['amount'])
    safe, _ = safe_amount(s)
    last_month = add_month(month(now), s['profile']['forecastMonths'] - 1)
    last_day = due(last_month, 31)
    rows = forecast(s, (last_day - now).days)
    monthly = []
    for row in rows:
        if not monthly or month(valid_date(row['date'])) != monthly[-1]['month']:
            monthly.append({'month': row['date'][:7], **row})
        else:
            monthly[-1] = {'month': row['date'][:7], **row}
    return {'asOf': now.isoformat(), 'bankBalance': ru(bank), 'assetValue': ru(assets), 'liabilities': ru(debt),
        'netWorth': ru(bank + assets - debt), 'protected': ru(protected), 'availableCash': ru(free(s, bs)),
        'safeToSpend': ru(max(0, safe)), 'cashShortfall': ru(max(0, -safe)), 'monthlyEMI': ru(emi_monthly),
        'monthlyBills': ru(bill_monthly), 'monthlyCommitments': ru(emi_monthly + bill_monthly + p(s['profile']['variableBudget'])),
        'emiRatio': round(ru(emi_monthly) / s['profile']['monthlyIncome'] * 100, 1) if s['profile']['monthlyIncome'] else 0,
        'actualExpense': ru(expenses), 'actualIncome': ru(income), 'categories': {k: ru(v) for k, v in cats.items()},
        'accounts': [{**a, 'balance': ru(bs[a['id']]), 'protected': ru(bs[a['id']] if not a['spendable'] else floor(a)),
                      'free': ru(bs[a['id']] - floor(a)) if a['spendable'] else 0} for a in s['accounts']],
        'emis': [{**e, 'remainingPrincipal': ru(loan_left(s, e)),
            'remainingPayments': e['months'] - sum(1 for t in s['transactions'] if t.get('ref', '').startswith('emi:' + e['id'] + ':')),
            'endMonth': add_month(e['startMonth'], e['months'] - 1)} for e in s['emis']],
        'upcoming': events(s, now, now + timedelta(days=30)), 'forecast': monthly,
        'fundingAlerts': list({b['account']: b for row in forecast(s, 30) for b in row['breaches']}.values()),
        'pf': [{'id': a['id'], 'value': a['value'], 'oneYear': pf_projection(a, 12), 'fiveYears': pf_projection(a, 60),
                'tenYears': pf_projection(a, 120)} for a in s['assets'] if a['kind'] == 'PF']}

def pf_projection(a, months):
    # Monthly approximation; EPS is a pension contribution, not an EPF corpus addition.
    value = p(a['value'])
    contribution = p(a.get('employee', 0)) + p(a.get('employerEPF', 0))
    rate = (1 + a.get('annualRate', 0) / 100) ** (1 / 12) - 1
    for _ in range(months):
        value = round(value * (1 + rate)) + contribution
    return ru(value)

def decision(s, req):
    price = p(number(req.get('price'), 'Purchase price', .01))
    name = text(req.get('name', 'This purchase'), 'Purchase name')
    pay = req.get('account')
    a = next((a for a in s['accounts'] if a['id'] == pay and a['spendable']), None)
    if not a:
        raise ValueError('Choose a spendable payment account.')
    months = number(req.get('months', 6), 'EMI months', 1, 60, True)
    rate = number(req.get('annualRate', 0), 'Annual interest rate', 0, 100)
    fees = p(number(req.get('fees', 0), 'Fees and taxes'))
    down = p(number(req.get('downPayment', 0), 'Down payment', 0, ru(price)))
    mode = choice(req.get('mode', 'cash'), ['cash', 'emi'], 'payment mode')
    principal = price - down
    monthly_rate = rate / 1200
    installment = round(principal / months) if monthly_rate == 0 else round(principal * monthly_rate / (1 - (1 + monthly_rate) ** -months))
    horizon = max(90, months * 31 + 31) if mode == 'emi' else 90
    base = forecast(s, horizon)
    scenario = forecast(s, horizon, purchase=price if mode == 'cash' else 0, pay_account=pay,
                        new_emi=installment if mode == 'emi' else 0, emi_months=months,
                        upfront=fees + (down if mode == 'emi' else 0))
    current = balances(s)[pay] - floor(a)
    upfront = price + fees if mode == 'cash' else down + fees
    minfree = min(p(r['available']) for r in scenario)
    breaches = sum(bool(r['breaches']) for r in scenario)
    safe, _ = safe_amount(s)
    required_buffer = p(s['profile']['comfortBuffer'])
    comfortable = current >= upfront and minfree >= required_buffer and breaches == 0
    status = 'BUY COMFORTABLY' if comfortable else 'WAIT' if minfree >= 0 and current >= upfront else 'FINANCIALLY RISKY'
    reasons = []
    if current < upfront:
        reasons.append(f'The payment account needs ₹{ru(upfront - current):,.2f} more above its protected floor. A transfer may be needed.')
    if minfree < 0:
        reasons.append(f'The projected discretionary cash shortfall reaches ₹{ru(-minfree):,.2f}.')
    elif minfree < required_buffer:
        reasons.append(f'Projected discretionary cash drops below your ₹{ru(required_buffer):,.2f} comfort buffer.')
    if breaches:
        reasons.append('At least one payment account drops below its reserve or minimum balance during the forecast. Review account funding.')
    if comfortable:
        reasons.append('The purchase fits the forecast while maintaining your account rules and comfort buffer.')
    recommended = None
    if mode == 'cash' and not comfortable:
        # Earliest future date with a safe 30-day window and enough funding in this account.
        long = forecast(s, 395)
        for i, row in enumerate(long[:365]):
            if i == 0:
                continue
            window = long[i:i + 31]
            acc_free = p(row['accountBalances'][pay]) - floor(a)
            if acc_free >= upfront and min(p(r['available']) for r in window) >= upfront + required_buffer and not any(r['breaches'] for r in window):
                recommended = row['date']
                break
    sample_dates = [r['date'] for r in base if valid_date(r['date']).day == monthrange(valid_date(r['date']).year, valid_date(r['date']).month)[1]]
    cash = forecast(s, horizon, purchase=price, pay_account=pay, upfront=fees)
    emi = forecast(s, horizon, pay_account=pay, new_emi=installment, emi_months=months, upfront=down + fees)
    maps = [{r['date']: r for r in values} for values in [base, cash, emi]]
    return {'name': name, 'status': status, 'reasons': reasons, 'safeToSpend': ru(max(0, safe)),
        'upfrontCost': ru(upfront), 'remainingToday': ru(free(s, balances(s)) - upfront),
        'lowestProjectedCash': ru(minfree), 'recommendedDate': recommended, 'monthlyEMI': ru(installment),
        'totalEMICost': ru(down + max(principal, installment * months) + fees), 'interestAndFees': ru(max(0, installment * months - principal) + fees),
        'horizonDays': horizon, 'simulation': [{'date': d, 'noPurchase': maps[0][d]['available'],
            'cash': maps[1][d]['available'], 'emi': maps[2][d]['available']} for d in sample_dates],
        'assumptions': ['Future salaries and planned budgets are estimates, not bank-confirmed transactions.',
            'Account reserves overlap minimum balances; the larger amount is protected.',
            'PF, EPS, FDs and other investments are excluded from purchase funding.',
            'EMI model uses a reducing-balance rate; enter all fees and taxes separately. No-cost EMI discounts and GST are not inferred.',
            'Loan principal changes only when an actual principal repayment is entered.']}

def demo_state():
    s = empty_state()
    t = today()
    m = month(t)
    opening = t.replace(day=1).isoformat()
    s['profile'].update({'name': 'Garvit', 'monthlyIncome': 120000, 'salaryDay': 3,
        'salaryAccount': 'hdfc', 'variableBudget': 15000, 'variableAccount': 'hdfc',
        'cashBuffer': 15000, 'comfortBuffer': 10000})
    s['accounts'] = [
        {'id':'hdfc','name':'HDFC Salary','bank':'HDFC Bank','purpose':'Salary and everyday spending','openingBalance':92400,'openingDate':opening,'minimum':10000,'reserve':10000,'spendable':True},
        {'id':'icici','name':'ICICI Emergency','bank':'ICICI Bank','purpose':'Emergency fund','openingBalance':150000,'openingDate':opening,'minimum':10000,'reserve':150000,'spendable':False},
        {'id':'post','name':'Post Office Savings','bank':'India Post','purpose':'IPO capital','openingBalance':150000,'openingDate':opening,'minimum':500,'reserve':150000,'spendable':False},
        {'id':'sbi','name':'SBI EMI Account','bank':'SBI','purpose':'EMIs and autopay','openingBalance':59600,'openingDate':opening,'minimum':3000,'reserve':20000,'spendable':True}]
    s['bills'] = [{'id':'rent','name':'Rent','category':'Housing','amount':18000,'dueDay':1,'account':'hdfc','startMonth':m,'endMonth':''},
        {'id':'sip','name':'Monthly SIP','category':'Investments','amount':10000,'dueDay':15,'account':'hdfc','startMonth':m,'endMonth':''},
        {'id':'utilities','name':'Utilities & internet','category':'Bills','amount':3500,'dueDay':10,'account':'hdfc','startMonth':m,'endMonth':''}]
    s['emis'] = [{'id':'phone','name':'iPhone','amount':4999,'principalOutstanding':34993,'annualRate':0,'months':7,'dueDay':8,'startMonth':m,'account':'sbi'},
        {'id':'car','name':'Car loan','amount':12500,'principalOutstanding':380000,'annualRate':9,'months':36,'dueDay':5,'startMonth':m,'account':'sbi'},
        {'id':'laptop','name':'Laptop','amount':4000,'principalOutstanding':20000,'annualRate':0,'months':5,'dueDay':20,'startMonth':m,'account':'sbi'}]
    s['assets'] = [{'id':'pf','name':'EPF retirement','kind':'PF','value':345000,'employee':6000,'employerEPF':4750,'employerEPS':1250,'annualRate':8,'asOf':t.isoformat()},
        {'id':'mf','name':'Mutual funds','kind':'Mutual fund','value':180000,'employee':0,'employerEPF':0,'employerEPS':0,'annualRate':0,'asOf':t.isoformat()},
        {'id':'cc','name':'Credit card outstanding','kind':'Credit card','value':32000,'employee':0,'employerEPF':0,'employerEPS':0,'annualRate':0,'asOf':t.isoformat()}]
    s['wishlist'] = [{'id':'airpods','name':'AirPods Pro','price':24900,'note':'Try the purchase planner'}, {'id':'trip','name':'A week away','price':80000,'note':'Travel fund'}]
    return s
