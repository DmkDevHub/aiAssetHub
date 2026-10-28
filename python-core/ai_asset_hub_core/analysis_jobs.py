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
        if preview['externalTransfer'] and not params['confirm_external'] or preview['paid'] and not params['confirm_paid']:raise LibraryError('MODEL_POLICY_DENIED')
        targets=AnalysisPlan(self.database).targets(params['plan']);identifier=str(uuid4())
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute("SELECT 1 FROM analysis_jobs WHERE status IN ('queued','running') LIMIT 1").fetchone():raise LibraryError('ANALYSIS_BUSY')
            manager=BudgetPolicy(self.db);policy=manager.check(params['plan']['model_id'],preview['estimatedUpperBoundUsd'],len(targets))
            policy['reservedUsd']=str(money(policy['reservedUsd'])+money(preview['estimatedUpperBoundUsd']));policy['requestsUsed']+=len(targets)
            manager.write(params['plan']['model_id'],policy)
            self.db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by,cost_limit) VALUES (?,?,?,?,?,'queued',strftime('%Y-%m-%dT%H:%M:%fZ','now'),'user',?)",(identifier,params['request_id'],payload,json.dumps({**preview['snapshot'],'inputVersions':preview['_inputVersions']}),len(targets),float(preview['estimatedUpperBoundUsd'])))
            self.db.executemany("INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,'queued')",[(identifier,row[0]) for row in targets])
            self.db.execute('COMMIT')
        except Exception:self.db.execute('ROLLBACK');raise
        return {'jobId':identifier,'reused':False}
