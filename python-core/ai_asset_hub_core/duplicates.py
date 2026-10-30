"""Explicit streaming SHA-256 jobs. Candidates never merge, remove or infer rights."""
import hashlib
import json
import os
import threading
from uuid import uuid4
from .analysis_input import source_info,validate_source_handle
from .bulk_metadata import identifiers,bounded
from .collections import Collections
from .database import Database
from .libraries import LibraryError,valid_id,ERROR_MESSAGES
from .transactions import WriteScope

MAX_BYTES=1_073_741_824
PREFIX='duplicates.job.'


def identity(info):return info.st_size,info.st_mtime_ns,info.st_dev,info.st_ino


def hash_file(database,item,canceled):
    owner,file=item['ownerId'],item['fileId']
    if canceled.is_set():raise LibraryError('USER_CANCELED')
    path,info=source_info(database,owner,file)
    if info.st_size>MAX_BYTES:raise LibraryError('INPUT_TOO_LARGE')
    if (info.st_size,info.st_mtime_ns)!=(item['size'],item['mtimeNs']):raise LibraryError('FILE_CHANGED')
    try:
        with open(path,'rb') as source:
            opened=validate_source_handle(database,owner,source)
            if identity(opened)!=identity(info):raise LibraryError('FILE_CHANGED')
            digest=hashlib.sha256();size=0
            while True:
                if canceled.is_set():raise LibraryError('USER_CANCELED')
                chunk=source.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>MAX_BYTES or size>info.st_size:raise LibraryError('FILE_CHANGED')
                digest.update(chunk)
            if canceled.is_set():raise LibraryError('USER_CANCELED')
            if size!=info.st_size or identity(os.fstat(source.fileno()))!=identity(info):raise LibraryError('FILE_CHANGED')
            _,current=source_info(database,owner,file)
            if identity(current)!=identity(info):raise LibraryError('FILE_CHANGED')
            scope=WriteScope(database.connection)
            try:
                row=database.connection.execute('SELECT size_bytes,mtime_ns FROM asset_files WHERE id=?',(file,)).fetchone()
                if not row or tuple(row)!=(item['size'],item['mtimeNs']):raise LibraryError('FILE_CHANGED')
                if canceled.is_set():raise LibraryError('USER_CANCELED')
                value=digest.hexdigest();database.connection.execute('UPDATE asset_files SET sha256=? WHERE id=?',(value,file));scope.commit()
                item['identity']=[info.st_dev,info.st_ino]
            except Exception:scope.rollback();raise
            return value
    except PermissionError:raise LibraryError('FILE_PERMISSION_DENIED') from None
    except FileNotFoundError:raise LibraryError('FILE_MISSING') from None
    except OSError:raise LibraryError('FILE_UNAVAILABLE') from None


def read(database,identifier):
    if not valid_id(identifier):raise LibraryError('INVALID_PARAMS')
    row=database.connection.execute('SELECT value_json FROM settings WHERE key=?',(PREFIX+identifier,)).fetchone()
    if not row:raise LibraryError('HASH_NOT_FOUND')
    return json.loads(row[0])


def save(database,identifier,value):
    database.connection.execute("INSERT INTO settings VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",(PREFIX+identifier,json.dumps(value)))


class DuplicateJobs:
    def __init__(self):self.controls={};self.lock=threading.Lock()

    def active(self,identifier):
        with self.lock:return identifier in self.controls and self.controls[identifier]['thread'].is_alive()

    def list(self,database,params):
        Collections.keys(params,'')
        rows=database.connection.execute("SELECT key,value_json FROM settings WHERE key LIKE 'duplicates.job.%' ORDER BY updated_at DESC,key DESC LIMIT 20").fetchall()
        return {'items':[{'id':key[len(PREFIX):],'status':(job:=json.loads(value))['status'],'total':len(job['items'])} for key,value in rows],'inferenceCalled':False}

    def start(self,database,params):
        Collections.keys(params,'asset_ids confirmed')
        if params['confirmed'] is not True:raise LibraryError('INVALID_PARAMS')
        assets=identifiers(params['asset_ids'],100)
        if not assets:raise LibraryError('INVALID_PARAMS')
        service=Collections(database)
        for asset in assets:service.require_asset(asset)
        rows=database.connection.execute('SELECT DISTINCT f.id,f.asset_id,f.size_bytes,f.mtime_ns FROM asset_file_members m JOIN asset_files f ON f.id=m.file_id JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 AND m.asset_id IN ('+','.join('?' for _ in assets)+') ORDER BY f.id',assets).fetchall()
        if not rows or len(rows)>100:raise LibraryError('BULK_LIMIT')
        identifier=str(uuid4());items=[dict(fileId=r[0],ownerId=r[1],size=r[2],mtimeNs=r[3],status='queued',sha256=None,errorCode=None) for r in rows]
        scope=WriteScope(database.connection)
        try:
            if database.connection.execute("SELECT 1 FROM settings WHERE key LIKE 'duplicates.job.%' AND json_extract(value_json,'$.status') IN ('queued','running') LIMIT 1").fetchone():raise LibraryError('HASH_BUSY')
            save(database,identifier,{'status':'queued','items':items})
            database.connection.execute("INSERT INTO audit_events VALUES (?,'user','duplicates.start','hash',?,'succeeded',strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",(str(uuid4()),identifier,json.dumps({'fileIds':[i['fileId'] for i in items],'total':len(items)})))
            scope.commit()
        except Exception:scope.rollback();raise
        control={'cancel':threading.Event()};thread=threading.Thread(target=self.run,args=(database.path,identifier,control),daemon=True);control['thread']=thread
        with self.lock:self.controls[identifier]=control
        thread.start();return {'jobId':identifier,'fileCount':len(items),'inferenceCalled':False}

    def run(self,path,identifier,control):
        database=None
        try:
            database=Database(path);job=read(database,identifier);job['status']='running';save(database,identifier,job)
            for item in job['items']:
                if control['cancel'].is_set():item.update(status='canceled',errorCode='USER_CANCELED');continue
                item['status']='running';save(database,identifier,job)
                try:item.update(sha256=hash_file(database,item,control['cancel']),status='hashed')
                except Exception as error:
                    code=str(error) if isinstance(error,LibraryError) and str(error) in ERROR_MESSAGES else 'INTERNAL_ERROR'
                    item.update(status='canceled' if code=='USER_CANCELED' else 'failed',errorCode=code)
                save(database,identifier,job)
            job['status']='canceled' if control['cancel'].is_set() else 'failed' if any(i['status']=='failed' for i in job['items']) else 'completed'
            save(database,identifier,job)
        except Exception:
            if database:
                try:
                    job=read(database,identifier);job['status']='failed'
                    for item in job['items']:
                        if item['status'] in ('queued','running'):item.update(status='failed',errorCode='DB_UNAVAILABLE')
                    save(database,identifier,job)
                except Exception:pass
        finally:
            if database:database.close()
            with self.lock:self.controls.pop(identifier,None)

    def status(self,database,params):
        Collections.keys(params,'job_id after_id');job=read(database,params['job_id']);cursor=params['after_id']
        if cursor is not None and cursor not in [i['fileId'] for i in job['items']]:raise LibraryError('INVALID_PARAMS')
        rows=[i for i in job['items'] if cursor is None or i['fileId']>cursor]
        return bounded({'jobId':params['job_id'],'status':job['status'],'total':len(job['items']),
            'processed':sum(i['status'] in ('hashed','failed','canceled') for i in job['items']),
            'hashed':sum(i['status']=='hashed' for i in job['items']),'failed':sum(i['status']=='failed' for i in job['items']),
            'canceled':sum(i['status']=='canceled' for i in job['items']),
            'needsRecovery':job['status'] in ('queued','running') and not self.active(params['job_id']),
            'items':[{key:i[key] for key in ('fileId','status','sha256','errorCode')} for i in rows[:4]],
            'next_cursor':rows[3]['fileId'] if len(rows)>4 else None,'inferenceCalled':False})

    def cancel(self,database,params):
        Collections.keys(params,'job_id');job=read(database,params['job_id'])
        if job['status'] not in ('queued','running'):return {'cancelRequested':False}
        with self.lock:control=self.controls.get(params['job_id'])
        if control:control['cancel'].set()
        else:
            scope=WriteScope(database.connection)
            try:
                # A worker may have completed between the initial read and lookup.
                job=read(database,params['job_id'])
                if job['status'] not in ('queued','running'):
                    scope.commit();return {'cancelRequested':False}
                job['status']='canceled'
                for item in job['items']:
                    if item['status'] in ('queued','running'):item.update(status='canceled',errorCode='CORE_INTERRUPTED')
                save(database,params['job_id'],job);scope.commit()
            except Exception:scope.rollback();raise
        return {'cancelRequested':True}

    def candidates(self,database,params):
        Collections.keys(params,'job_id after_hash after_file_id');job=read(database,params['job_id']);groups={};stale=0
        for item in job['items']:
            if item['status']!='hashed':continue
            try:
                _,info=source_info(database,item['ownerId'],item['fileId'])
                row=database.connection.execute('SELECT relative_path,sha256 FROM asset_files WHERE id=?',(item['fileId'],)).fetchone()
                if (info.st_size,info.st_mtime_ns)!=(item['size'],item['mtimeNs']) or item.get('identity')!=[info.st_dev,info.st_ino] or row[1]!=item['sha256']:stale+=1;continue
            except LibraryError:stale+=1;continue
            assets=[r[0] for r in database.connection.execute('SELECT asset_id FROM asset_file_members WHERE file_id=? ORDER BY asset_id',(item['fileId'],))]
            groups.setdefault((item['sha256'],item['size']),[]).append({'fileId':item['fileId'],'name':row[0][-160:],
                'logicalAssetIds':assets[:16],'logicalAssetCount':len(assets)})
        rows=[{'sha256':key[0],'size':key[1],'files':value,'fileCount':len(value),'logicalEquivalence':'not-determined','rightsEquivalence':'not-determined'} for key,value in sorted(groups.items()) if len(value)>1]
        cursor=params['after_hash']
        if cursor is not None and cursor not in [r['sha256'] for r in rows]:raise LibraryError('INVALID_PARAMS')
        rows=[r for r in rows if cursor is None or r['sha256']>cursor]
        file_cursor=params['after_file_id'];next_file=None
        if file_cursor is not None and (not rows or file_cursor not in [f['fileId'] for f in rows[0]['files']]):raise LibraryError('INVALID_PARAMS')
        if rows:
            files=[f for f in rows[0]['files'] if file_cursor is None or f['fileId']>file_cursor]
            next_file=files[3]['fileId'] if len(files)>4 else None;rows[0]['files']=files[:4]
        return bounded({'items':rows[:1],'next_cursor':rows[0]['sha256'] if len(rows)>1 else None,'staleCount':stale,'inferenceCalled':False,
            'next_file_cursor':next_file,'filesPerGroupLimit':4,'automaticMerge':False,'automaticDelete':False})

    def close(self):
        with self.lock:controls=list(self.controls.values())
        for control in controls:control['cancel'].set()
        for control in controls:control['thread'].join(5)
