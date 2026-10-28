"""Explicit asynchronous embedding operations; never resumed on process startup."""
import json
import struct
from uuid import uuid4
from .analysis_engine import AnalysisEngine
from .embeddings import Embeddings,embed,vector
from .libraries import LibraryError,valid_id


class EmbeddingEngine(AnalysisEngine):
    def start(self,database,params):
        if not isinstance(params,dict) or set(params)!={'selected','confirmed'} or params['confirmed'] is not True:raise LibraryError('INVALID_PARAMS')
        pairs=params['selected']
        if not isinstance(pairs,list) or not 1<=len(pairs)<=100:raise LibraryError('INVALID_PARAMS')
        service=Embeddings(database);profile=service.profile()
        if not profile:raise LibraryError('EMBEDDING_NOT_READY')
        documents=service.documents();seen=set()
        for pair in pairs:
            if not isinstance(pair,dict) or set(pair)!={'asset_id','result_id'} or not valid_id(pair['asset_id']) or not valid_id(pair['result_id']) or pair['asset_id'] in seen:raise LibraryError('INVALID_PARAMS')
            seen.add(pair['asset_id']);doc=documents.get(pair['asset_id'])
            if not doc or doc['resultId']!=pair['result_id']:raise LibraryError('EMBEDDING_RESULT_CHANGED')
        return self.queue(database,{'kind':'generate','profile':profile,'selected':pairs,'total':len(pairs)})

    def query(self,database,params):
        if not isinstance(params,dict) or set(params)!={'query','mode','confirmed'} or params['confirmed'] is not True or params['mode']!='semantic' or not isinstance(params['query'],str) or not 1<=len(params['query'].strip())<=256:raise LibraryError('INVALID_PARAMS')
        service=Embeddings(database);profile=service.profile()
        if not profile or not service.ready(profile):raise LibraryError('EMBEDDING_NOT_READY')
        return self.queue(database,{'kind':'query','profile':profile,'query':params['query'].strip(),'mode':params['mode'],'total':1})

    def queue(self,database,job):
        with self.lock:
            if self.controls:raise LibraryError('EMBEDDING_BUSY')
        identifier=str(uuid4());job.update(id=identifier,status='queued',processed=0,failed=0,errors=[])
        database.connection.execute("INSERT INTO settings VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",('embedding.work.'+identifier,json.dumps(job)))
        self.launch(identifier);return {'jobId':identifier}

    def run(self,identifier,control):
        from .database import Database
        database=None;job=None
        try:
            database=Database(self.path);db=database.connection;service=Embeddings(database)
            job=json.loads(db.execute('SELECT value_json FROM settings WHERE key=?',('embedding.work.'+identifier,)).fetchone()[0]);job['status']='running';self.save(db,job)
            profile=job['profile']
            if job['kind']=='query':
                from .semantic_search import search
                job['results']=search(database,job,control);job.update(status='completed',processed=1);self.save(db,job);return
            for pair in job['selected']:
                if control['cancel'].is_set():raise LibraryError('USER_CANCELED')
                try:
                    service.fresh(profile);doc=service.documents().get(pair['asset_id'])
                    if not doc or doc['resultId']!=pair['result_id']:raise LibraryError('EMBEDDING_RESULT_CHANGED')
                    def register(connection):
                        control['connection']=connection
                        if connection.sock:control['socket']=connection.sock
                    values=vector(embed(profile,doc['text'],False,control['cancel'],register),profile['dimension'])
                    service.fresh(profile);current=service.documents().get(doc['id'])
                    if not current or current['fingerprint']!=doc['fingerprint']:raise LibraryError('EMBEDDING_RESULT_CHANGED')
                    db.execute('BEGIN IMMEDIATE')
                    try:
                        if service.profile()!=profile or service.documents().get(doc['id'],{}).get('fingerprint')!=doc['fingerprint']:raise LibraryError('EMBEDDING_RESULT_CHANGED')
                        db.execute("INSERT INTO asset_embeddings VALUES (?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(asset_id,embedding_model) DO UPDATE SET result_id=excluded.result_id,dimension=excluded.dimension,vector_blob=excluded.vector_blob,input_fingerprint=excluded.input_fingerprint,created_at=excluded.created_at",
                                   (doc['id'],doc['resultId'],profile['version'],profile['dimension'],struct.pack('<'+'f'*len(values),*values),doc['fingerprint']))
                        db.execute('COMMIT')
                    except Exception:db.execute('ROLLBACK');raise
                except LibraryError as error:
                    job['failed']+=1
                    if len(job['errors'])<10:job['errors'].append({'assetId':pair['asset_id'],'code':str(error)})
                job['processed']+=1;self.save(db,job)
            job['status']='failed' if job['failed'] else 'completed';self.save(db,job)
        except Exception as error:
            if database and job:
                from .libraries import ERROR_MESSAGES
                job['status']='canceled' if control['cancel'].is_set() else 'failed';job['error']=str(error) if isinstance(error,LibraryError) and str(error) in ERROR_MESSAGES else 'EMBEDDING_FAILED'
                try:self.save(database.connection,job)
                except Exception:pass
        finally:
            if database:database.close()
            with self.lock:self.controls.pop(identifier,None)

    @staticmethod
    def save(db,job):
        db.execute("UPDATE settings SET value_json=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE key=?",(json.dumps(job),'embedding.work.'+job['id']))


def work_status(database,params):
    if not isinstance(params,dict) or set(params)!={'job_id'} or not valid_id(params['job_id']):raise LibraryError('INVALID_PARAMS')
    row=database.connection.execute('SELECT value_json FROM settings WHERE key=?',('embedding.work.'+params['job_id'],)).fetchone()
    if not row:raise LibraryError('INVALID_PARAMS')
    job=json.loads(row[0]);return {k:job[k] for k in ('id','kind','status','total','processed','failed','errors','error','results') if k in job}
