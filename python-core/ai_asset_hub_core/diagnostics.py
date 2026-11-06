"""Bounded allowlisted diagnostic projection. No arbitrary log/JSON export or inference."""
import json
from decimal import Decimal,InvalidOperation
from .libraries import LibraryError,valid_id,ERROR_MESSAGES


def cost(value):
    if not isinstance(value,str) or len(value)>40:return None
    try:
        number=Decimal(value)
        return str(number) if number.is_finite() and 0<=number<=100000 else None
    except InvalidOperation:return None


def code(value):return value if value in ERROR_MESSAGES else 'INTERNAL_ERROR' if value else None


class Diagnostics:
    def __init__(self,database):self.db=database.connection

    def read(self,params):
        if not isinstance(params,dict) or set(params)-{'kind','after_id'} or params.get('kind') not in ('analysis','unity','audit'):raise LibraryError('INVALID_PARAMS')
        kind=params['kind'];cursor=params.get('after_id')
        if cursor is not None and not valid_id(cursor):raise LibraryError('INVALID_PARAMS')
        table={'analysis':'analysis_runs','unity':'unity_operations','audit':'audit_events'}[kind]
        values=[];condition=''
        if cursor:
            row=self.db.execute(f'SELECT rowid FROM {table} WHERE id=?',(cursor,)).fetchone()
            if not row:raise LibraryError('INVALID_PARAMS')
            condition='WHERE rowid<?';values=[row[0]]
        rows=self.db.execute(f'SELECT id FROM {table} {condition} ORDER BY rowid DESC LIMIT 11',values).fetchall()
        items=[self.item(kind,row[0]) for row in rows[:10]]
        result=dict(kind=kind,items=items,next_cursor=rows[9][0] if len(rows)>10 else None,modelCalled=False)
        if len(json.dumps(result,ensure_ascii=True).encode())>12000:raise LibraryError('DIAGNOSTIC_LIMIT')
        return result

    def item(self,kind,identifier):
        if kind=='analysis':
            row=self.db.execute('SELECT job_id,asset_id,status,usage_json,error_json,created_at FROM analysis_runs WHERE id=?',(identifier,)).fetchone()
            usage=json.loads(row[3] or '{}');error=json.loads(row[4] or '{}')
            projected={k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','prompt_eval_count','eval_count') and type(v) is int and 0<=v<=10**12}
            projected['providerRequestAttempted']=usage.get('providerRequestAttempted') is True
            projected['providerReportedCostUsd']=cost(usage.get('providerReportedCostUsd'))
            return dict(id=identifier,jobId=row[0],assetId=row[1],status=row[2],usage=projected,errorCode=code(error.get('code')),createdAt=row[5])
        if kind=='unity':
            row=self.db.execute('SELECT action,status,created_at,result_json FROM unity_operations WHERE id=?',(identifier,)).fetchone()
            raw=json.loads(row[3] or '{}');result=raw.get('result') or {};items=result.get('items') or []
            return dict(id=identifier,action=row[0] if row[0] in ('import','place') else 'other',status=row[1] if row[1] in ('queued','unknown','succeeded','failed','partial','cancelled') else 'unknown',
                createdAt=row[2],itemCount=len(items),copiedCount=sum(i.get('copied') is True for i in items),errorCode=code(result.get('errorCode')))
        row=self.db.execute('SELECT action,outcome,created_at,details_redacted_json FROM audit_events WHERE id=?',(identifier,)).fetchone()
        from .mcp_audit import TOOLS
        raw=json.loads(row[3])
        return dict(id=identifier,action=row[0] if row[0] in TOOLS else 'other',status=row[1] if row[1] in ('succeeded','denied','failed') else 'unknown',createdAt=row[2],errorCode=code(raw.get('errorCode')))

    def budget(self,params):
        if params!={}:raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute("SELECT key,value_json FROM settings WHERE key LIKE 'model.policy.%' ORDER BY key LIMIT 51").fetchall()
        if len(rows)>50:raise LibraryError('DIAGNOSTIC_LIMIT')
        items=[]
        for key,raw in rows:
            identifier=key[len('model.policy.'):]
            if not valid_id(identifier):continue
            value=json.loads(raw)
            items.append(dict(modelId=identifier,budgetUsd=cost(value.get('budgetUsd')),reservedUpperBoundUsd=cost(value.get('reservedUsd')),
                reservedRequests=value.get('requestsUsed') if type(value.get('requestsUsed')) is int and 0<=value['requestsUsed']<=10**12 else None))
        return dict(items=items,costMeaning='conservative-reservation-not-invoice',reportedUsageMeaning='provider-reported-not-verified-billing',modelCalled=False)
