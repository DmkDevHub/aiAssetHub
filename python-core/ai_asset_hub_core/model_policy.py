"""Persistent opt-in and hard limits. Decimal USD, never inferred free pricing."""
import json
from decimal import Decimal, InvalidOperation
from .libraries import LibraryError


def money(value):
    if not isinstance(value,str) or len(value)>40:raise LibraryError('INVALID_PARAMS')
    try:amount=Decimal(value)
    except InvalidOperation:raise LibraryError('INVALID_PARAMS') from None
    if not amount.is_finite() or amount<0 or amount>100000:raise LibraryError('INVALID_PARAMS')
    return amount


class BudgetPolicy:
    def __init__(self, db):self.db=db

    def read(self, identifier):
        row=self.db.execute('SELECT value_json FROM settings WHERE key=?',('model.policy.'+identifier,)).fetchone()
        return json.loads(row[0]) if row else {'allowExternal':False,'allowPaid':False,'budgetUsd':'0','maxRequests':100,'reservedUsd':'0','requestsUsed':0}

    def write(self, identifier, policy):
        self.db.execute("INSERT INTO settings VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",('model.policy.'+identifier,json.dumps(policy)))

    def check(self, identifier, amount, count=1, reserve=False):
        cost=money(amount)
        if type(count) is not int or not 1<=count<=10000:raise LibraryError('INVALID_PARAMS')
        if reserve:self.db.execute('BEGIN IMMEDIATE')
        try:
            policy=self.read(identifier)
            if policy['requestsUsed']+count>policy['maxRequests'] or money(policy['reservedUsd'])+cost>money(policy['budgetUsd']):
                raise LibraryError('BUDGET_EXCEEDED')
            if reserve:
                policy['requestsUsed']+=count;policy['reservedUsd']=str(money(policy['reservedUsd'])+cost)
                self.write(identifier,policy);self.db.execute('COMMIT')
            return policy
        except Exception:
            if reserve:self.db.execute('ROLLBACK')
            raise
