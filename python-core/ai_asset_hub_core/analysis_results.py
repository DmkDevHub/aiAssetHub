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
