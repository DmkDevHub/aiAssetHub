"""Read immutable analysis results without invoking any provider."""
import json
from .annotations import AnnotationService
from .libraries import LibraryError


class AssetAnalysis:
    def __init__(self,database):self.database=database;self.db=database.connection

    def get(self, params):
        if not isinstance(params,dict) or set(params)!={'asset_id'}:raise LibraryError('INVALID_PARAMS')
        AnnotationService(self.database).require_asset(params['asset_id'])
        row=self.db.execute('''SELECT r.id,r.description,r.tags_json,r.created_at,run.model_snapshot_json,run.input_fingerprint
            FROM asset_active_results ar JOIN analysis_results r ON r.id=ar.analysis_result_id JOIN analysis_runs run ON run.id=r.run_id
            WHERE ar.asset_id=?''',(params['asset_id'],)).fetchone()
        if not row:return {'active':None}
        snapshot=json.loads(row[4])
        return {'active':{'id':row[0],'description':row[1],'tags':json.loads(row[2]),'createdAt':row[3],
                          'provider':snapshot.get('provider'),'modelId':snapshot.get('modelId'),'profileVersion':snapshot.get('profileVersion'),
                          'inputFingerprint':row[5]}}

    def history(self, params):
        from .libraries import valid_id,ERROR_MESSAGES
        if not isinstance(params,dict) or set(params)-{'asset_id','after_id'} or not valid_id(params.get('asset_id')) or params.get('after_id') is not None and not valid_id(params['after_id']):raise LibraryError('INVALID_PARAMS')
        AnnotationService(self.database).require_asset(params['asset_id'])
        clause='';values=[params['asset_id']]
        if params.get('after_id'):
            cursor=self.db.execute('SELECT created_at,rowid FROM analysis_runs WHERE id=? AND asset_id=?',(params['after_id'],params['asset_id'])).fetchone()
            if not cursor:raise LibraryError('INVALID_PARAMS')
            clause=' AND (run.created_at<? OR (run.created_at=? AND run.rowid<?))';values.extend((cursor[0],cursor[0],cursor[1]))
        rows=self.db.execute("""SELECT run.id,run.status,run.created_at,run.model_snapshot_json,run.input_fingerprint,run.error_json,r.id,r.description,r.tags_json,
            EXISTS(SELECT 1 FROM asset_active_results ar WHERE ar.analysis_result_id=r.id) FROM analysis_runs run
            LEFT JOIN analysis_results r ON r.run_id=run.id WHERE run.asset_id=?"""+clause+' ORDER BY run.created_at DESC,run.rowid DESC LIMIT 2',values).fetchall()
        items=[]
        for row in rows[:1]:
            snapshot=json.loads(row[3]);error=json.loads(row[5]) if row[5] else {}
            item={'id':row[0],'status':row[1],'createdAt':row[2],'provider':snapshot.get('provider'),'modelId':snapshot.get('modelId'),
                  'profileVersion':snapshot.get('profileVersion'),'inputFingerprint':row[4],'errorCode':error.get('code') if error.get('code') in ERROR_MESSAGES else 'INTERNAL_ERROR' if error else None,
                  'resultId':row[6],'description':row[7],'tags':json.loads(row[8]) if row[8] else [],'active':bool(row[9])}
            if len(json.dumps(item,ensure_ascii=False).encode('utf-8'))>12000:raise LibraryError('DB_UNAVAILABLE')
            items.append(item)
        return {'items':items,'next_cursor':items[-1]['id'] if len(rows)>1 else None}
