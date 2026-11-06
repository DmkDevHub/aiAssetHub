"""Explicit, expiring Unity plans and Core-owned durable operation records."""
from datetime import datetime,timezone
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4
from .libraries import LibraryError,valid_id
from .unity_targets import UnityTargets
from .unity_metadata import UnityMetadata
from .mcp_files import McpFiles
from .mcp_queries import McpQueries
from .session_file import no_links

MAX_BYTES=16*1024*1024


def png_snapshot(path):
    """Read only an explicitly planned source; reject change, links and oversized decode."""
    from PIL import Image
    try:
        path=Path(path);no_links(path);before=path.stat()
        if not path.is_file() or not 0<before.st_size<=MAX_BYTES:raise ValueError()
        with path.open('rb') as source:raw=source.read(MAX_BYTES+1)
        if len(raw)!=before.st_size or not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError()
        import io
        with Image.open(io.BytesIO(raw)) as image:
            if image.format!='PNG' or image.width*image.height>16777216 or getattr(image,'n_frames',1)!=1:raise ValueError()
            image.verify()
        after=path.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):raise ValueError()
        return dict(size=before.st_size,mtimeNs=str(before.st_mtime_ns),sha256=hashlib.sha256(raw).hexdigest())
    except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):raise LibraryError('UNITY_SOURCE_INVALID') from None


class UnityOperations:
    def __init__(self,database):
        self.database=database;self.db=database.connection;self.targets=UnityTargets(database)

    def _target(self,identifier):
        target=self.targets.target(identifier);directory,state=self.targets.mailbox().connect(target['path'])
        if state.get('playing') is not False or state.get('compiling') is not False:raise LibraryError('UNITY_EDITOR_BUSY')
        return target,directory,state

    def _store_plan(self,value):
        rows=self.db.execute("SELECT key FROM settings WHERE key LIKE 'unity.plan.%' ORDER BY updated_at DESC,key DESC").fetchall()
        for row in rows[19:]:self.db.execute('DELETE FROM settings WHERE key=?',(row[0],))
        identifier=str(uuid4());value.update(id=identifier,expiresAt=time.time()+300)
        self.db.execute("INSERT INTO settings VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",('unity.plan.'+identifier,json.dumps(value,ensure_ascii=False)))
        return self.public_plan(value)

    @staticmethod
    def public_plan(value):
        return dict(planId=value['id'],targetId=value['targetId'],action=value['action'],projectPath=value['projectPath'],
            editorVersion=value['editorVersion'],expiresAt=value['expiresAt'],items=[{k:v for k,v in i.items() if k!='sourcePath'} for i in value['items']],
            issues=['RIGHTS_REVIEW_REQUIRED','COMPATIBILITY_UNVERIFIED'],requiresExecutionApproval=True,planOnly=True,modelCalled=False,
            **({k:value[k] for k in ('scene','sceneHandle','position','rotation','scale','name')} if value['action']=='place' else {}))

    def preview_import(self,params):
        if not isinstance(params,dict) or set(params)!={'target_id','asset_ids'}:raise LibraryError('INVALID_PARAMS')
        identifiers=params['asset_ids']
        if not isinstance(identifiers,list) or not 1<=len(identifiers)<=20 or any(not valid_id(i) for i in identifiers) or len(set(identifiers))!=len(identifiers):raise LibraryError('INVALID_PARAMS')
        target,_,state=self._target(params['target_id']);items=[];seen=set();total=0
        metadata=UnityMetadata(self.database,[Path(target['path'])])
        for asset in identifiers:
            metadata.describe(asset)
            files=McpFiles(self.database,McpQueries.safe_path).get(asset)['files']
            sources=[f for f in files if set(f['roles'])&{'source','dependency'}]
            if len(sources)!=1 or sources[0]['kind']!='PNG':raise LibraryError('UNITY_FORMAT_UNSUPPORTED')
            file=sources[0]
            if file['availability']!='present' or not file.get('path'):raise LibraryError('UNITY_SOURCE_INVALID')
            if file['dependencies']['items'] or file['dependencies']['unresolvedDeclarationCount']:raise LibraryError('UNITY_FORMAT_UNSUPPORTED')
            relative='Assets/AIAssetHub/'+file['id']+'.png';destination=Path(target['path'])/relative
            try:
                no_links(destination);no_links(Path(str(destination)+'.meta'))
                if destination.exists() or Path(str(destination)+'.meta').exists() or file['id'] in seen:raise LibraryError('UNITY_TARGET_CONFLICT')
            except (OSError,ValueError):raise LibraryError('UNITY_TARGET_CONFLICT') from None
            if Path(file['path']).is_relative_to(Path(target['path'])):raise LibraryError('UNITY_SOURCE_INVALID')
            snapshot=png_snapshot(file['path']);total+=snapshot['size'];seen.add(file['id'])
            if total>64*1024*1024:raise LibraryError('UNITY_LIMIT')
            items.append(dict(assetId=asset,fileId=file['id'],sourcePath=file['path'],targetRelativePath=relative,**snapshot))
        return self._store_plan(dict(action='import',targetId=target['id'],projectPath=target['path'],session=state['session'],editorVersion=state['editorVersion'],items=items))

    def _plan(self,identifier):
        if not valid_id(identifier):raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT value_json FROM settings WHERE key=?',('unity.plan.'+identifier,)).fetchone()
        if not row:raise LibraryError('UNITY_PLAN_EXPIRED')
        value=json.loads(row[0])
        if value['expiresAt']<time.time() or value.get('consumed'):raise LibraryError('UNITY_PLAN_EXPIRED')
        return value

    def execute_import(self,params):return self._execute(params,'import')

    def preview_place(self,params):
        import math
        if not isinstance(params,dict) or set(params)!={'target_id','import_operation_id','position','rotation','scale','name'}:raise LibraryError('INVALID_PARAMS')
        for key,bound in (('position',100000),('rotation',360000),('scale',1000)):
            value=params[key]
            if not isinstance(value,list) or len(value)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>bound or key=='scale' and abs(x)<.0001 for x in value):raise LibraryError('INVALID_PARAMS')
        name=params['name']
        if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 for c in name):raise LibraryError('INVALID_PARAMS')
        target,_,state=self._target(params['target_id'])
        if state.get('prefabStage') or type(state.get('sceneRevision')) is not int:raise LibraryError('UNITY_EDITOR_BUSY')
        operation=self.status(dict(operation_id=params['import_operation_id']))
        if operation['action']!='import' or operation['targetId']!=target['id'] or operation['status'] not in ('succeeded','partial'):raise LibraryError('UNITY_IMPORT_REQUIRED')
        raw=json.loads(self.db.execute('SELECT result_json FROM unity_operations WHERE id=?',(operation['operationId'],)).fetchone()[0])
        if raw['session']!=state['session']:raise LibraryError('UNITY_SESSION_CHANGED')
        successful={r['fileId']:r for r in operation['result']['items'] if r['status']=='succeeded'}
        items=[]
        for source in raw['plan']['items']:
            if source['fileId'] in successful:
                item={k:v for k,v in source.items() if k!='sourcePath'};item['guid']=successful[source['fileId']]['guid']
                path=Path(target['path'])/item['targetRelativePath']
                if png_snapshot(path)['sha256']!=item['sha256']:raise LibraryError('UNITY_SOURCE_CHANGED')
                items.append(item)
        if not items:raise LibraryError('UNITY_IMPORT_REQUIRED')
        return self._store_plan(dict(action='place',targetId=target['id'],projectPath=target['path'],session=state['session'],editorVersion=state['editorVersion'],
            scene=state['scene'],sceneHandle=state['sceneHandle'],sceneRevision=state['sceneRevision'],position=params['position'],rotation=params['rotation'],scale=params['scale'],name=name,items=items))

    def execute_place(self,params):return self._execute(params,'place')

    def _execute(self,params,action):
        if not isinstance(params,dict) or set(params)!={'plan_id','request_id','confirmed','rights_confirmed','compatibility_confirmed'} or any(params[k] is not True for k in ('confirmed','rights_confirmed','compatibility_confirmed')) or not valid_id(params['request_id']):raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT id,result_json FROM unity_operations WHERE request_id=?',(params['request_id'],)).fetchone()
        if row:
            stored=json.loads(row[1])
            if stored['plan']['id']!=params['plan_id'] or stored['plan']['action']!=action:raise LibraryError('INVALID_PARAMS')
            return self.status(dict(operation_id=row[0]))
        plan=self._plan(params['plan_id'])
        if plan['action']!=action:raise LibraryError('INVALID_PARAMS')
        target,directory,state=self._target(plan['targetId'])
        if plan['session']!=state['session']:raise LibraryError('UNITY_SESSION_CHANGED')
        if action=='place' and (any(plan[k]!=state.get(k) for k in ('scene','sceneHandle','sceneRevision')) or state.get('prefabStage')):raise LibraryError('UNITY_SCENE_CHANGED')
        if action=='import':
            # Re-resolve registration/composition and hash before dispatch; Editor hashes again.
            for item in plan['items']:
                current=McpFiles(self.database,McpQueries.safe_path).get(item['assetId'])['files']
                file=next((f for f in current if f['id']==item['fileId'] and 'source' in f['roles']),None)
                if not file or file.get('path')!=item['sourcePath'] or png_snapshot(item['sourcePath'])!={k:item[k] for k in ('size','mtimeNs','sha256')}:raise LibraryError('UNITY_SOURCE_CHANGED')
                destination=Path(target['path'])/item['targetRelativePath']
                try:
                    no_links(destination);no_links(Path(str(destination)+'.meta'))
                    if destination.exists() or Path(str(destination)+'.meta').exists():raise LibraryError('UNITY_TARGET_CONFLICT')
                except (OSError,ValueError):raise LibraryError('UNITY_TARGET_CONFLICT') from None
        identifier=str(uuid4());stored=dict(plan=plan,session=state['session'],deadline=time.time()+60,result=None)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._plan(params['plan_id'])
            plan['consumed']=True
            self.db.execute('UPDATE settings SET value_json=? WHERE key=?',(json.dumps(plan),'unity.plan.'+plan['id']))
            self.db.execute("INSERT INTO unity_operations VALUES (?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",(identifier,params['request_id'],plan['items'][0]['assetId'],target['path'],action,'queued',json.dumps(stored)))
            self.db.execute('COMMIT')
        except Exception:self.db.execute('ROLLBACK');raise
        try:self.targets.mailbox().send(target['path'],action,self._fields(plan),identifier)
        except LibraryError:
            self.db.execute("UPDATE unity_operations SET status='unknown' WHERE id=?",(identifier,))
            raise
        return self.status(dict(operation_id=identifier))

    @staticmethod
    def _fields(plan):
        return dict(items=plan['items'],**({k:plan[k] for k in ('scene','sceneHandle','sceneRevision','position','rotation','scale','name')} if plan['action']=='place' else {}))

    def status(self,params):
        if not isinstance(params,dict) or set(params)!={'operation_id'} or not valid_id(params['operation_id']):raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT id,status,result_json FROM unity_operations WHERE id=?',(params['operation_id'],)).fetchone()
        if not row:raise LibraryError('UNITY_OPERATION_NOT_FOUND')
        stored=json.loads(row[2]);plan=stored['plan'];status=row[1];error=None
        if status in ('queued','unknown'):
            try:
                self.targets.target(plan['targetId'])
                result=self.targets.mailbox().result(plan['projectPath'],row[0],stored['session'])
                if result:
                    stored['result']=self._validate_result(plan,result);status=result['status']
                    self.db.execute('UPDATE unity_operations SET status=?,result_json=? WHERE id=?',(status,json.dumps(stored),row[0]))
            except LibraryError as failure:error=str(failure)
            if status=='queued' and time.time()>stored['deadline']:
                status='unknown';self.db.execute("UPDATE unity_operations SET status='unknown' WHERE id=?",(row[0],))
        return dict(operationId=row[0],targetId=plan['targetId'],action=plan['action'],status=status,
            result=stored['result'],errorCode=error,mayHaveSideEffects=status=='unknown',modelCalled=False)

    @staticmethod
    def _validate_result(plan,result):
        import re
        items=result.get('items') or []
        if not items and result['status']=='failed':return dict(status='failed',errorCode='UNITY_EDITOR_REJECTED',items=[])
        if len(items)!=len(plan['items']):raise LibraryError('UNITY_INVALID_RESULT')
        safe=[]
        for item,expected in zip(items,plan['items']):
            if item.get('assetId')!=expected['assetId'] or item.get('fileId')!=expected['fileId'] or item.get('status') not in ('succeeded','failed','cancelled'):raise LibraryError('UNITY_INVALID_RESULT')
            if item.get('assetPath') and item['assetPath']!=expected['targetRelativePath']:raise LibraryError('UNITY_INVALID_RESULT')
            guid=item.get('guid') or None
            if item['status']=='succeeded' and (not isinstance(guid,str) or not re.fullmatch('[a-f0-9]{32}',guid) or item.get('assetPath')!=expected['targetRelativePath']):raise LibraryError('UNITY_INVALID_RESULT')
            safe.append(dict(assetId=item['assetId'],fileId=item['fileId'],status=item['status'],assetPath=item.get('assetPath') or None,guid=guid,
                copied=item.get('copied') is True,errorCode=None if item['status']=='succeeded' else 'UNITY_ITEM_FAILED'))
            if plan['action']=='place' and item['status']=='succeeded':
                entity=item.get('entityId')
                if (not isinstance(entity,str) or not re.fullmatch('[0-9]{1,20}',entity) or not 0<int(entity)<2**64 or item.get('objectId')!=f"session:{plan['session']}:entity:{entity}" or
                    item.get('scene')!=plan['scene'] or item.get('sceneHandle')!=plan['sceneHandle'] or item.get('sceneDirty') is not True or item.get('sceneSaved') is not False or
                    item.get('objectName')!=plan['name']):raise LibraryError('UNITY_INVALID_RESULT')
                for key in ('position','rotation','scale'):
                    import math
                    vector=item.get(key)
                    if not isinstance(vector,list) or len(vector)!=3 or any(type(x) not in (float,int) or not math.isfinite(x) for x in vector):raise LibraryError('UNITY_INVALID_RESULT')
                    if key!='rotation' and any(abs(a-b)>max(.0001,abs(b)*1e-5) for a,b in zip(vector,plan[key])):raise LibraryError('UNITY_INVALID_RESULT')
                safe[-1].update({key:item[key] for key in ('objectId','entityId','objectName','scene','sceneHandle','position','rotation','scale','sceneDirty','sceneSaved')})
        derived='succeeded' if all(i['status']=='succeeded' for i in safe) else 'failed' if all(i['status']=='failed' for i in safe) else 'partial'
        if result['status']!=derived:raise LibraryError('UNITY_INVALID_RESULT')
        return dict(status=derived,items=safe)
