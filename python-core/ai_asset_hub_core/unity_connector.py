"""Windows Editor private mailbox. Only probe projects supplied by a trusted allowlist."""
from datetime import datetime, timezone, timedelta
import json
import secrets
from pathlib import Path
from uuid import uuid4
from .session_file import no_links, private
from .transport import _unique_object
from .libraries import LibraryError, valid_id
from .unity_metadata import UnityMetadata


def read_private(path, limit=16384):
    private(path)
    with Path(path).open('rb') as source:raw=source.read(limit+1)
    if len(raw)>limit:raise ValueError()
    return json.loads(raw,object_pairs_hook=_unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))


def write_private(path, value):
    path=Path(path);no_links(path)
    if len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8'))>16384:raise ValueError()
    temporary=path.with_name('.'+str(uuid4())+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as output:
            private(temporary,True);json.dump(value,output,ensure_ascii=False,allow_nan=False)
        # Request IDs are unique; never overwrite a command.
        if path.exists():raise ValueError()
        temporary.rename(path)
    finally:temporary.unlink(missing_ok=True)


class EditorMailbox:
    def __init__(self,database,allowed_projects):
        self.metadata=UnityMetadata(database,allowed_projects)

    def connect(self,project):
        path,version=self.metadata.project(project)
        directory=path/'Library'/'AIAssetHub'
        try:
            private(directory)
            state=read_private(directory/'connector.json')
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(state['updatedAt'])).total_seconds()
            if not 0<=age<10 or type(state['protocol']) is not int or state['protocol']!=1 or Path(state['project'])!=path or state['editorVersion']!=version:raise ValueError()
            import re
            if not valid_id(state['session']) or not isinstance(state['token'],str) or not re.fullmatch('[0-9a-f]{64}',state['token']):raise ValueError()
            if type(state['pid']) is not int or state['pid']<=0:raise ValueError()
            if any(type(state.get(k)) is not bool for k in ('playing','compiling','sceneDirty','batchMode')):raise ValueError()
            if not isinstance(state.get('scene'),str) or len(state['scene'])>2048 or not isinstance(state.get('sceneHandle'),str) or len(state['sceneHandle'])>80:raise ValueError()
            return directory,state
        except (OSError,ValueError,KeyError,TypeError):raise LibraryError('UNITY_NOT_CONNECTED') from None

    def send(self,project,action,fields=None,identifier=None):
        directory,state=self.connect(project);identifier=identifier or str(uuid4())
        request=dict(id=identifier,session=state['session'],token=state['token'],action=action,
            expiresAt=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat(),**(fields or {}))
        try:write_private(directory/(identifier+'.request.json'),request)
        except (OSError,ValueError):raise LibraryError('UNITY_CHANNEL_UNAVAILABLE') from None
        return identifier,state['session']

    def result(self,project,identifier,session):
        if not valid_id(identifier) or not valid_id(session):raise LibraryError('INVALID_PARAMS')
        directory,state=self.connect(project)
        if state['session']!=session:raise LibraryError('UNITY_SESSION_CHANGED')
        path=directory/(identifier+'.result.json')
        if not path.exists():return None
        try:
            result=read_private(path)
            if result['id']!=identifier or result['session']!=session or not secrets.compare_digest(result['token'],state['token']):raise ValueError()
            if result['status'] not in ('succeeded','failed','partial','cancelled'):raise ValueError()
            # Only known public fields leave the mailbox; never forward token or descriptor.
            public=dict(status=result['status'],errorCode=result.get('errorCode') or None)
            if result.get('items') is not None:public['items']=result['items']
            return public
        except (OSError,ValueError,KeyError,TypeError):raise LibraryError('UNITY_INVALID_RESULT') from None

    @staticmethod
    def public(state):
        return {key:state[key] for key in ('pid','project','editorVersion','scene','sceneHandle','sceneDirty','playing','compiling','batchMode')}
