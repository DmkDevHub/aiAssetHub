"""Explicit background scans keep desktop health/IPC responsive. No analysis or auto resume."""
import json
import threading
from uuid import uuid4
from .database import Database
from .assets import AssetService
from .libraries import LibraryError,valid_id


class ScanJobs:
    def __init__(self):self.thread=None;self.stop=threading.Event();self.current=None

    def start(self,database,params):
        if not isinstance(params,dict) or set(params)!={'library_id'} or not valid_id(params['library_id']):raise LibraryError('INVALID_PARAMS')
        if self.thread and self.thread.is_alive():
            if self.current[1]==params['library_id']:return dict(jobId=self.current[0],reused=True)
            raise LibraryError('SCAN_BUSY')
        if not database.connection.execute('SELECT 1 FROM library_roots WHERE id=? AND enabled=1',(params['library_id'],)).fetchone():raise LibraryError('LIBRARY_NOT_FOUND')
        identifier=str(uuid4());self.current=(identifier,params['library_id']);self.stop.clear()
        value=dict(jobId=identifier,libraryId=params['library_id'],status='queued',result=None,errorCode=None)
        self.write(database,identifier,value)
        def run():
            worker=None
            try:
                worker=Database(database.path);value['status']='running';self.write(worker,identifier,value)
                value['result']=AssetService(worker).scan(params,self.stop);value['status']='completed'
            except Exception as error:
                value['status']='cancelled' if str(error)=='SCAN_CANCELLED' else 'failed';value['errorCode']='SCAN_CANCELLED' if value['status']=='cancelled' else 'SCAN_FAILED'
            finally:
                if worker:
                    try:self.write(worker,identifier,value)
                    finally:worker.close()
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()
        return dict(jobId=identifier,reused=False)

    @staticmethod
    def write(database,identifier,value):
        database.connection.execute("INSERT INTO settings VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",('scan.job.'+identifier,json.dumps(value)))

    def status(self,database,params):
        if not isinstance(params,dict) or set(params)!={'job_id'} or not valid_id(params['job_id']):raise LibraryError('INVALID_PARAMS')
        row=database.connection.execute('SELECT value_json FROM settings WHERE key=?',('scan.job.'+params['job_id'],)).fetchone()
        if not row:raise LibraryError('SCAN_NOT_FOUND')
        value=json.loads(row[0])
        if value['status'] in ('queued','running') and not (self.thread and self.thread.is_alive() and self.current and self.current[0]==params['job_id']):value['status']='interrupted'
        return value

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(2)
