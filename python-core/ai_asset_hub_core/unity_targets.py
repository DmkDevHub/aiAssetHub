"""Desktop-owned project allowlist. MCP can list targets but cannot grant access."""
import json
from pathlib import Path
from uuid import uuid4
from .libraries import LibraryError,valid_id,_local_path
from .session_file import no_links
from .unity_metadata import UnityMetadata
from .unity_connector import EditorMailbox

KEY='unity.targets.v1'


class UnityTargets:
    def __init__(self,database):self.database=database;self.db=database.connection

    def records(self):
        row=self.db.execute('SELECT value_json FROM settings WHERE key=?',(KEY,)).fetchone()
        return json.loads(row[0]) if row else []

    def target(self,identifier):
        if not valid_id(identifier):raise LibraryError('INVALID_PARAMS')
        row=next((r for r in self.records() if r['id']==identifier),None)
        if row is None:raise LibraryError('UNITY_TARGET_NOT_ALLOWED')
        return row

    def mailbox(self):return EditorMailbox(self.database,[Path(r['path']) for r in self.records()])

    def save(self,params):
        if not isinstance(params,dict) or set(params)!={'project_path','confirmed'} or params['confirmed'] is not True:raise LibraryError('INVALID_PARAMS')
        value=params['project_path']
        if not isinstance(value,str) or not value or len(value)>2048:raise LibraryError('INVALID_PARAMS')
        path=Path(value)
        try:_local_path(path);no_links(path)
        except (OSError,ValueError):raise LibraryError('UNITY_PROJECT_UNAVAILABLE') from None
        UnityMetadata(self.database,[path]).project(value)
        rows=self.records()
        for row in rows:
            if Path(row['path'])==path:return dict(id=row['id'],registered=True)
        if len(rows)>=10:raise LibraryError('UNITY_LIMIT')
        row=dict(id=str(uuid4()),path=str(path));rows.append(row);self._write(rows)
        return dict(id=row['id'],registered=True)

    def remove(self,params):
        if not isinstance(params,dict) or set(params)!={'target_id','confirmed'} or params['confirmed'] is not True:raise LibraryError('INVALID_PARAMS')
        row=self.target(params['target_id']);self._write([r for r in self.records() if r['id']!=row['id']])
        return dict(id=row['id'],registered=False)

    def _write(self,rows):
        if len(json.dumps(rows,ensure_ascii=True).encode())>8000:raise LibraryError('UNITY_LIMIT')
        self.db.execute("INSERT INTO settings VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",(KEY,json.dumps(rows)))

    def list(self,params):
        if params!={}:raise LibraryError('INVALID_PARAMS')
        items=[];mailbox=self.mailbox()
        for row in self.records():
            item=dict(id=row['id'],projectPath=row['path'],connected=False,errorCode=None)
            try:
                _,state=mailbox.connect(row['path']);public=mailbox.public(state);public.pop('project',None);item.update(connected=True,**public)
            except LibraryError as error:item['errorCode']=str(error)
            items.append(item)
        result=dict(items=items,modelCalled=False)
        if len(json.dumps(result,ensure_ascii=True).encode())>12000:raise LibraryError('UNITY_LIMIT')
        return result
