from datetime import date
import copy
import pytest
from backend import finance as f

@pytest.fixture
def sample(monkeypatch):
    monkeypatch.setattr(f, 'today', lambda:date(2026,10,1))
    s=f.empty_state()
    s['profile'].update(monthlyIncome=0,salaryDay=3,variableBudget=0,cashBuffer=0,comfortBuffer=0)
    s['accounts']=[{'id':'bank','name':'Salary','bank':'HDFC','purpose':'Everyday','openingBalance':100000,'openingDate':'2026-10-01','minimum':10000,'reserve':20000,'spendable':True},
        {'id':'locked','name':'Emergency','bank':'ICICI','purpose':'Protected','openingBalance':200000,'openingDate':'2026-10-01','minimum':0,'reserve':200000,'spendable':False}]
    return s

def test_reserve_overlap_and_pf_not_spendable(sample):
    sample['assets']=[{'id':'pf','name':'PF','kind':'PF','value':500000,'asOf':'2026-10-01','employee':1000,'employerEPF':1000,'employerEPS':1000,'annualRate':0}]
    snap=f.summary(f.validate(sample))
    assert snap['safeToSpend']==80000
    assert snap['netWorth']==800000
    assert snap['protected']==220000
    assert snap['pf'][0]['oneYear']==524000

def test_transfers_do_not_create_income_or_expense(sample):
    sample['transactions']=[{'id':'t','name':'Move money','date':'2026-10-01','amount':10000,'type':'transfer','category':'Transfer','account':'bank','toAccount':'locked','ref':'','principalPaid':0}]
    snap=f.summary(f.validate(sample))
    assert snap['bankBalance']==300000
    assert snap['actualExpense']==0
    assert snap['actualIncome']==0
    assert snap['safeToSpend']==70000

def test_overdue_bill_reserved_and_paid_once(sample):
    sample['bills']=[{'id':'rent','name':'Rent','category':'Housing','amount':20000,'dueDay':30,'account':'bank','startMonth':'2026-09','endMonth':'2026-09'}]
    assert f.summary(sample)['safeToSpend']==60000
    assert f.summary(sample)['upcoming'][0]['overdue']
    t={'id':'t','name':'Rent paid','date':'2026-10-01','amount':20000,'type':'expense','category':'Housing','account':'bank','ref':'bill:rent:2026-09','principalPaid':0}
    sample['transactions']=[t]
    assert f.summary(f.validate(sample))['safeToSpend']==60000
    assert not f.summary(sample)['upcoming']
    sample['transactions'].append({**t,'id':'u'})
    with pytest.raises(ValueError,match='already recorded'):f.validate(sample)

def test_variable_budget_remaining_no_double_count(sample):
    sample['profile'].update(variableBudget=31000,variableAccount='bank')
    sample['transactions']=[{'id':'t','name':'Food','date':'2026-10-01','amount':10000,'type':'expense','category':'Food','account':'bank','ref':'','principalPaid':0}]
    snap=f.summary(sample)
    assert snap['safeToSpend']==49000
    assert snap['actualExpense']==10000

def test_salary_not_added_twice(sample):
    sample['profile'].update(monthlyIncome=120000,salaryDay=1,salaryAccount='bank')
    sample['transactions']=[{'id':'t','name':'Salary','date':'2026-10-01','amount':120000,'type':'income','category':'Salary','account':'bank','ref':'salary:2026-10','principalPaid':0}]
    rows=f.forecast(f.validate(sample),2)
    assert all(r['income']==0 for r in rows)
    assert rows[0]['bankBalance']==420000

def test_short_month_last_day_and_emi_end(sample):
    assert f.due('2027-02',31)==date(2027,2,28)
    sample['emis']=[{'id':'phone','name':'Phone','amount':5000,'principalOutstanding':10000,'annualRate':0,'months':2,'dueDay':31,'startMonth':'2026-10','account':'bank'}]
    ev=f.events(sample,date(2026,10,1),date(2027,1,1))
    assert [e['dueDate'] for e in ev]==['2026-10-31','2026-11-30']

def test_actual_principal_not_total_emi_reduces_debt(sample):
    sample['emis']=[{'id':'loan','name':'Loan','amount':10000,'principalOutstanding':100000,'annualRate':10,'months':12,'dueDay':1,'startMonth':'2026-10','account':'bank'}]
    sample['transactions']=[{'id':'t','name':'Loan','date':'2026-10-01','amount':10000,'type':'expense','category':'EMI','account':'bank','ref':'emi:loan:2026-10','principalPaid':8000}]
    snap=f.summary(f.validate(sample))
    assert snap['liabilities']==92000
    assert snap['emis'][0]['remainingPayments']==11

def test_cash_emi_comparison_and_fees(sample):
    r=f.decision(sample,{'name':'Laptop','price':60000,'account':'bank','mode':'emi','months':6,'annualRate':0,'fees':1200,'downPayment':0})
    assert r['monthlyEMI']==10000
    assert r['totalEMICost']==61200
    assert r['interestAndFees']==1200
    assert r['status']=='BUY COMFORTABLY'
    assert r['simulation'][-1]['emi']==r['simulation'][-1]['cash']

def test_negative_account_cannot_hide_behind_other_account(sample):
    sample['accounts'].append({'id':'other','name':'Other','bank':'SBI','purpose':'Spending','openingBalance':100000,'openingDate':'2026-10-01','minimum':0,'reserve':0,'spendable':True})
    sample['bills']=[{'id':'rent','name':'Rent','category':'Housing','amount':95000,'dueDay':2,'account':'bank','startMonth':'2026-10','endMonth':'2026-10'}]
    r=f.decision(sample,{'name':'Shoes','price':1000,'account':'other'})
    assert r['status']!='BUY COMFORTABLY'
    assert any('payment account' in reason for reason in r['reasons'])

def test_money_precision_validation(sample):
    sample['accounts'][0]['openingBalance']=1.001
    with pytest.raises(ValueError,match='two decimal'):f.validate(sample)

def test_forecast_has_requested_number_of_calendar_months(sample):
    sample['profile']['forecastMonths']=12
    snap=f.summary(sample)
    assert len(snap['forecast'])==12
    assert snap['forecast'][-1]['month']=='2027-09'

def test_unsafe_purchase_and_protected_account(sample):
    r=f.decision(sample,{'name':'Car','price':100001,'account':'bank'})
    assert r['status']=='FINANCIALLY RISKY'
    with pytest.raises(ValueError,match='spendable'):f.decision(sample,{'name':'Car','price':1,'account':'locked'})
