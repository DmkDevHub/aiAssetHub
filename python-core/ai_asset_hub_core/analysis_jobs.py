"""Explicit, idempotent job creation and atomic conservative budget reservation."""
import json
from uuid import uuid4
from .libraries import LibraryError, valid_id
from .analysis_plan import AnalysisPlan
from .model_policy import BudgetPolicy,money


class AnalysisJobs:
    def __init__(self,database):self.database=database;self.db=database.connection

    def start(self, params):
        if not isinstance(params,dict) or set(params)!={'plan','plan_token','request_id','confirmed','confirm_external','confirm_paid'} or not valid_id(params['request_id']):raise LibraryError('INVALID_PARAMS')
        if params['confirmed'] is not True or any(type(params[k]) is not bool for k in ('confirm_external','confirm_paid')) or not isinstance(params['plan_token'],str) or len(params['plan_token'])!=64:raise LibraryError('INVALID_PARAMS')
        payload=json.dumps(params,sort_keys=True)
        existing=self.db.execute('SELECT id,scope_json FROM analysis_jobs WHERE request_id=?',(params['request_id'],)).fetchone()
        if existing:
            if existing[1]!=payload:raise LibraryError('INVALID_PARAMS')
            return {'jobId':existing[0],'reused':True}
        preview=AnalysisPlan(self.database).preview(params['plan'],internal=True)
        if preview['planToken']!=params['plan_token']:raise LibraryError('ANALYSIS_PLAN_CHANGED')
        if not preview['targetCount']:raise LibraryError('ANALYSIS_EMPTY')
        if not preview['eligibleCount']:raise LibraryError('ANALYSIS_NO_SUPPORTED_INPUT')
        if preview['externalTransfer'] and not params['confirm_external'] or preview['paid'] and not params['confirm_paid']:raise LibraryError('MODEL_POLICY_DENIED')
        targets=AnalysisPlan(self.database).targets(params['plan']);identifier=str(uuid4())
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute("SELECT 1 FROM analysis_jobs WHERE status IN ('queued','running') LIMIT 1").fetchone():raise LibraryError('ANALYSIS_BUSY')
            manager=BudgetPolicy(self.db);policy=manager.check(params['plan']['model_id'],preview['estimatedUpperBoundUsd'],preview['eligibleCount'])
            policy['reservedUsd']=str(money(policy['reservedUsd'])+money(preview['estimatedUpperBoundUsd']));policy['requestsUsed']+=preview['eligibleCount']
            manager.write(params['plan']['model_id'],policy)
            self.db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by,cost_limit) VALUES (?,?,?,?,?,'queued',strftime('%Y-%m-%dT%H:%M:%fZ','now'),'user',?)",(identifier,params['request_id'],payload,json.dumps({**preview['snapshot'],'inputVersions':preview['_inputVersions']}),len(targets),float(preview['estimatedUpperBoundUsd'])))
            self.db.executemany("INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,'queued')",[(identifier,row[0]) for row in targets])
            self.db.execute('COMMIT')
        except Exception:self.db.execute('ROLLBACK');raise
        return {'jobId':identifier,'reused':False}

    def status(self, params, active=False):
        if not isinstance(params,dict) or set(params)!={'job_id'} or not valid_id(params['job_id']):raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT status,requested_count FROM analysis_jobs WHERE id=?',(params['job_id'],)).fetchone()
        if not row:raise LibraryError('ANALYSIS_NOT_FOUND')
        counts=dict(self.db.execute('SELECT status,count(*) FROM analysis_job_items WHERE job_id=? GROUP BY status',(params['job_id'],)))
        from .libraries import ERROR_MESSAGES
        errors=[{'assetId':r[0],'code':r[1] if r[1] in ERROR_MESSAGES else 'INTERNAL_ERROR'} for r in self.db.execute('SELECT asset_id,error_code FROM analysis_job_items WHERE job_id=? AND error_code IS NOT NULL ORDER BY asset_id LIMIT 10',(params['job_id'],))]
        return {'jobId':params['job_id'],'status':row[0],'total':row[1], 'processed':sum(counts.get(k,0) for k in ('completed','failed','canceled')),
                'succeeded':counts.get('completed',0),'failed':counts.get('failed',0),'canceled':counts.get('canceled',0),
                'active':active,'needsRecovery':row[0] in ('queued','running') and not active,'errors':errors,
                'partialSuccess':counts.get('completed',0)>0 and (counts.get('failed',0)>0 or counts.get('canceled',0)>0)}

    def list(self, params):
        if params!={}:raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute('SELECT id,status,requested_count,created_at FROM analysis_jobs ORDER BY created_at DESC,rowid DESC LIMIT 20').fetchall()
        return {'items':[{'id':r[0],'status':r[1],'total':r[2],'createdAt':r[3]} for r in rows]}

    def cancel_orphan(self, params):
        status=self.status(params)
        if status['status'] not in ('queued','running'):return {'cancelRequested':False,'status':status['status']}
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute("UPDATE analysis_runs SET status='canceled',error_json='{\"code\":\"CORE_INTERRUPTED\"}' WHERE job_id=? AND status='running'",(params['job_id'],))
            self.db.execute("UPDATE analysis_job_items SET status='canceled',error_code='CORE_INTERRUPTED',ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE job_id=? AND status IN ('queued','running')",(params['job_id'],))
            self.db.execute("UPDATE analysis_jobs SET status='canceled',ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(params['job_id'],))
            self.db.execute('COMMIT')
        except Exception:self.db.execute('ROLLBACK');raise
        return {'cancelRequested':True,'status':'canceled'}

    def retry_plan(self, params):
        status=self.status(params)
        if status['status'] in ('queued','running'):raise LibraryError('ANALYSIS_BUSY')
        row=self.db.execute('SELECT scope_json FROM analysis_jobs WHERE id=?',(params['job_id'],)).fetchone()
        old=json.loads(row[0])
        if not isinstance(old.get('plan'),dict):raise LibraryError('INVALID_PARAMS')
        return {'plan':old['plan'],'previousJobId':params['job_id'],'requiresReview':True}
