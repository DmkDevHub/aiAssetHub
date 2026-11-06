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
