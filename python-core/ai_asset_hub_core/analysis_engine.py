"""One approved persisted job at a time; slow inference never blocks the pipe."""
import json
import socket
import threading
from uuid import uuid4
from .libraries import LibraryError


class AnalysisEngine:
    def __init__(self,database):
        self.path=database.path;self.controls={};self.lock=threading.Lock()

    def launch(self,identifier):
        with self.lock:
            if identifier in self.controls:return
            control={'cancel':threading.Event(),'connection':None}
            thread=threading.Thread(target=self.run,args=(identifier,control),daemon=True)
            control['thread']=thread;self.controls[identifier]=control;thread.start()

    def active(self,identifier):
        with self.lock:return identifier in self.controls and self.controls[identifier]['thread'].is_alive()

    def cancel(self,identifier):
        with self.lock:control=self.controls.get(identifier)
        if not control:return False
        control['cancel'].set();connection=control['connection']
        connection_socket=control.get('socket') or (connection.sock if connection else None)
        if connection_socket:
            try:connection_socket.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            if connection:connection.close()
        return True

    def close(self):
        with self.lock:controls=list(self.controls.items())
        for identifier,_ in controls:self.cancel(identifier)
        for _,control in controls:control['thread'].join(5)

    def run(self,identifier,control):
        from .database import Database
        from .analysis_input import prepare_image,prepare_audio,prepare_geometry,prepare_animation,prepare_text,source_info
        from .models import ModelService
        from .inference import infer
        from .annotations import AnnotationService
        database=None
        try:
            database=Database(self.path);db=database.connection
            row=db.execute('SELECT model_snapshot_json FROM analysis_jobs WHERE id=? AND status=\'queued\'',(identifier,)).fetchone()
            if not row:return
            snapshot=json.loads(row[0]);versions=snapshot.pop('inputVersions')
            db.execute("UPDATE analysis_jobs SET status='running',started_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(identifier,))
            items=[r[0] for r in db.execute("SELECT asset_id FROM analysis_job_items WHERE job_id=? AND status='queued' ORDER BY asset_id",(identifier,))]
            for asset_id in items:
                if control['cancel'].is_set():
                    db.execute("UPDATE analysis_job_items SET status='canceled',error_code='USER_CANCELED',ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE job_id=? AND asset_id=?",(identifier,asset_id));continue
                run=str(uuid4());usage={'providerRequestAttempted':False}
                db.execute('BEGIN IMMEDIATE')
                try:
                    db.execute("UPDATE analysis_job_items SET status='running',attempts=attempts+1,started_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE job_id=? AND asset_id=?",(identifier,asset_id))
                    db.execute("INSERT INTO analysis_runs(id,job_id,asset_id,model_snapshot_json,input_fingerprint,status,created_at) VALUES (?,?,?,?,'','running',strftime('%Y-%m-%dT%H:%M:%fZ','now'))",(run,identifier,asset_id,json.dumps(snapshot)))
                    db.execute('COMMIT')
                except Exception:db.execute('ROLLBACK');raise
                try:
                    from .analysis_contract import contract
                    approved=snapshot.get('analysisContract')
                    if approved is not None and {k:v for k,v in approved.items() if k!='reviewInputFingerprint'}!=contract(database):
                        raise LibraryError('ANALYSIS_PLAN_CHANGED')
                    try:checked=ModelService(database).validate({'id':snapshot['registryId'],'modality':snapshot.get('inputModality','image')},reserved=True)
                    except OSError:raise LibraryError('MODEL_POLICY_DENIED') from None
                    if not checked['compatible']:raise LibraryError(checked['reason'])
                    if checked['snapshot']['profileVersion']!=snapshot['profileVersion']:raise LibraryError('MODEL_CHANGED')
                    prepared=(prepare_text if snapshot.get('inputModality')=='text' else prepare_animation if snapshot.get('analysisInputKind')=='animation' else prepare_geometry if snapshot.get('analysisInputKind')=='threeD' else prepare_audio if snapshot.get('inputModality')=='audio' else prepare_image)(database,asset_id,versions[asset_id])
                    from .providers import inspect_local,inspect_external
                    if snapshot['kind']=='local':
                        try:current=inspect_local(snapshot['modelId'])
                        except Exception:raise LibraryError('MODEL_UNAVAILABLE') from None
                        if current.get('status')!='available' or not snapshot['inspection'].get('metadataVersion') or current.get('metadataVersion')!=snapshot['inspection']['metadataVersion']:raise LibraryError('MODEL_CHANGED')
                    else:
                        try:current=inspect_external(snapshot['modelId'])
                        except Exception:raise LibraryError('MODEL_UNAVAILABLE') from None
                        if current.get('status')!='available' or any(current.get(k)!=snapshot['inspection'].get(k) for k in ('pricing','contextLength','modalities','costClass')):raise LibraryError('MODEL_CHANGED')
                    db.execute('UPDATE analysis_runs SET input_fingerprint=? WHERE id=?',(prepared['fingerprint'],run))
                    if control['cancel'].is_set():raise LibraryError('USER_CANCELED')
                    try:key=ModelService(database).vault.read(snapshot['registryId']) if snapshot['kind']=='external' else None
                    except OSError:raise LibraryError('MODEL_POLICY_DENIED') from None
                    usage['providerRequestAttempted']=True
                    def register(connection):
                        control['connection']=connection
                        if connection.sock:control['socket']=connection.sock
                    output,usage=infer(snapshot,prepared,control['cancel'],register,key)
                    if control['cancel'].is_set():raise LibraryError('USER_CANCELED')
                    if not isinstance(output,dict) or set(output)-{'description','tags','suggestions','audioSuggestions'} or not {'description','tags'}<=set(output) or not isinstance(output['description'],str) or not 1<=len(output['description'].strip())<=1024:raise LibraryError('INVALID_MODEL_OUTPUT')
                    from .analysis_features import suggestions,VERSION
                    features={'schema':VERSION,'technical':prepared.get('technical',{}),
                        'suggestions':suggestions(output.get('suggestions',{})),'suggestionStatus':'proposed'}
                    if prepared.get('previewKind')=='wireframe' and (features['suggestions']['colors'] or features['suggestions']['material'] or features['suggestions'].get('action')):raise LibraryError('INVALID_MODEL_OUTPUT')
                    if snapshot.get('inputModality')=='audio':
                        from .analysis_features import audio_suggestions
                        features['audioSuggestions']=audio_suggestions(output.get('audioSuggestions',{}))
                    elif 'audioSuggestions' in output:raise LibraryError('INVALID_MODEL_OUTPUT')
                    try:labels=AnnotationService.labels(output['tags'])
                    except LibraryError:raise LibraryError('INVALID_MODEL_OUTPUT') from None
                    if sum(map(len,labels.values()))>512:raise LibraryError('INVALID_MODEL_OUTPUT')
                    path,info=source_info(database,asset_id)
                    if (info.st_size,info.st_mtime_ns)!=(prepared['size'],prepared['mtimeNs']):raise LibraryError('FILE_CHANGED')
                    result=str(uuid4());db.execute('BEGIN IMMEDIATE')
                    try:
                        db.execute("UPDATE analysis_runs SET status='completed',usage_json=? WHERE id=?",(json.dumps(usage),run))
                        db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES (?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",(result,run,asset_id,output['description'].strip(),json.dumps(list(labels.values())),json.dumps(features)))
                        db.execute("INSERT INTO asset_active_results VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(asset_id) DO UPDATE SET analysis_result_id=excluded.analysis_result_id,selected_at=excluded.selected_at",(asset_id,result))
                        db.execute("DELETE FROM asset_tags WHERE asset_id=? AND source='ai'",(asset_id,))
                        for normalized,label in labels.items():
                            db.execute('INSERT OR IGNORE INTO tags(id,label,normalized_label) VALUES (?,?,?)',(str(uuid4()),label,normalized))
                            db.execute("INSERT INTO asset_tags(asset_id,tag_id,source,analysis_result_id) SELECT ?,id,'ai',? FROM tags WHERE normalized_label=?",(asset_id,result,normalized))
                        db.execute('UPDATE asset_files SET sha256=? WHERE asset_id=?',(prepared['fingerprint'],asset_id))
                        db.execute("UPDATE analysis_job_items SET status='completed',ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE job_id=? AND asset_id=?",(identifier,asset_id))
                        db.execute('COMMIT')
                    except Exception:db.execute('ROLLBACK');raise
                except Exception as error:
                    from .libraries import ERROR_MESSAGES
                    code='FILE_PERMISSION_DENIED' if isinstance(error,PermissionError) else 'FILE_MISSING' if isinstance(error,FileNotFoundError) else 'FILE_UNAVAILABLE' if isinstance(error,OSError) else str(error) if isinstance(error,LibraryError) and str(error) in ERROR_MESSAGES else 'INTERNAL_ERROR'
                    state='canceled' if control['cancel'].is_set() or code=='USER_CANCELED' else 'failed'
                    db.execute('BEGIN IMMEDIATE')
                    try:
                        db.execute('UPDATE analysis_runs SET status=?,usage_json=?,error_json=? WHERE id=?',(state,json.dumps(usage),json.dumps({'code':code}),run))
                        db.execute("UPDATE analysis_job_items SET status=?,error_code=?,ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE job_id=? AND asset_id=?",(state,code,identifier,asset_id))
                        db.execute('COMMIT')
                    except Exception:db.execute('ROLLBACK');raise
            failed=db.execute("SELECT 1 FROM analysis_job_items WHERE job_id=? AND status='failed' LIMIT 1",(identifier,)).fetchone()
            state='canceled' if control['cancel'].is_set() else 'failed' if failed else 'completed'
            db.execute("UPDATE analysis_jobs SET status=?,ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(state,identifier))
        except Exception:
            if database and database.connection:
                try:
                    db=database.connection
                    db.execute("UPDATE analysis_job_items SET status='failed',error_code='DB_UNAVAILABLE' WHERE job_id=? AND status IN ('queued','running')",(identifier,))
                    db.execute("UPDATE analysis_runs SET status='failed',error_json='{\"code\":\"DB_UNAVAILABLE\"}' WHERE job_id=? AND status='running'",(identifier,))
                    db.execute("UPDATE analysis_jobs SET status='failed',ended_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(identifier,))
                except Exception:pass
        finally:
            if database:database.close()
            with self.lock:self.controls.pop(identifier,None)
