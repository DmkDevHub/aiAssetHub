"""Persist explicit model profiles without invoking providers or inference."""
import json
import unicodedata
from uuid import uuid4
from .libraries import LibraryError, valid_id


class ModelService:
    def __init__(self, database):
        if database is None or getattr(database,'connection',None) is None:
            raise LibraryError('DB_UNAVAILABLE')
        self.db=database.connection
        self.database=database

    @property
    def vault(self):
        from .credentials import Vault
        return Vault(self.database.path)

    @staticmethod
    def text(value, limit):
        if not isinstance(value,str) or not value.strip() or len(value)>limit or any(unicodedata.category(c).startswith('C') for c in value):
            raise LibraryError('INVALID_PARAMS')
        return value.strip()

    def register(self, params):
        if not isinstance(params,dict) or set(params)!={'provider_name','kind','model_id','modalities'}:
            raise LibraryError('INVALID_PARAMS')
        name=self.text(params['provider_name'],80)
        model=self.text(params['model_id'],160)
        kind=params['kind']; modalities=params['modalities']
        if kind not in ('local','external') or not isinstance(modalities,list) or not modalities or len(modalities)>3 or any(m not in ('text','image','audio') for m in modalities) or len(set(modalities))!=len(modalities):
            raise LibraryError('INVALID_PARAMS')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            provider=self.db.execute('SELECT id FROM model_providers WHERE name=? AND kind=?',(name,kind)).fetchone()
            provider_id=provider[0] if provider else str(uuid4())
            if not provider: self.db.execute('INSERT INTO model_providers VALUES (?,?,?)',(provider_id,name,kind))
            row=self.db.execute('SELECT id FROM model_registry WHERE provider_id=? AND model_id=?',(provider_id,model)).fetchone()
            identifier=row[0] if row else str(uuid4())
            if not row:
                self.db.execute("INSERT INTO model_registry(id,provider_id,model_id,modalities_json,capabilities_json) VALUES (?,?,?,?,?)",(identifier,provider_id,model,json.dumps(modalities),json.dumps({'verified':False})))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK'); raise
        return {'id':identifier,'created':row is None}

    def list(self, params):
        if not isinstance(params,dict) or set(params)-{'after_id'} or (params.get('after_id') is not None and not valid_id(params['after_id'])):
            raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute('''SELECT m.id,p.name,p.kind,m.model_id,m.modalities_json,m.enabled,m.capabilities_json
            FROM model_registry m JOIN model_providers p ON p.id=m.provider_id
            WHERE m.id>? ORDER BY m.id LIMIT 11''',(params.get('after_id') or '',)).fetchall()
        items=[{'id':r[0],'provider':r[1],'kind':r[2],'modelId':r[3],'modalities':json.loads(r[4]),'enabled':bool(r[5]),'inspection':json.loads(r[6])} for r in rows[:10]]
        for item in items:
            try:item['hasCredential']=self.vault.read(item['id']) is not None
            except OSError:item['hasCredential']=False
        bounded=[];size=0
        for item in items:
            length=len(json.dumps(item,ensure_ascii=False).encode('utf-8'))
            if length>10000:raise LibraryError('DB_UNAVAILABLE')
            if bounded and size+length>12000:break
            bounded.append(item);size+=length
        return {'items':bounded,'next_cursor':bounded[-1]['id'] if len(rows)>len(bounded) else None}

    def inspect(self, params):
        if not isinstance(params,dict) or set(params)-{'id','allow_external'} or not valid_id(params.get('id')) or not isinstance(params.get('allow_external',False),bool): raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT p.name,p.kind,m.model_id FROM model_registry m JOIN model_providers p ON p.id=m.provider_id WHERE m.id=?',(params['id'],)).fetchone()
        if not row: raise LibraryError('INVALID_PARAMS')
        from .providers import inspect_local, inspect_external
        result={'status':'unsupported_provider','modalities':[]}
        if row[0].casefold()=='ollama' and row[1]=='local':
            try: result=inspect_local(row[2])
            except Exception: result={'status':'unavailable','modalities':[]}
        if row[1]=='external' and row[0].casefold()=='openrouter':
            if not params.get('allow_external',False):result={'status':'external_consent_required','modalities':[]}
            else:
                try:result=inspect_external(row[2])
                except Exception:result={'status':'unavailable','modalities':[]}
        result['metadataRequestAttempted']=row[0].casefold()=='ollama' and row[1]=='local' and not row[2].endswith(':cloud') or row[0].casefold()=='openrouter' and row[1]=='external' and params.get('allow_external',False)
        from datetime import datetime, timezone
        result.update(checkedAt=datetime.now(timezone.utc).isoformat(),inferenceCalled=False,verified=result['status']=='available')
        self.db.execute('UPDATE model_registry SET capabilities_json=?,enabled=0 WHERE id=?',(json.dumps(result),params['id']))
        return result

    def credential(self, params):
        if not isinstance(params,dict) or set(params)-{'id','action','key','allow_external'} or not valid_id(params.get('id')) or params.get('action') not in ('save','delete','test'):
            raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT p.name,p.kind,m.capabilities_json FROM model_registry m JOIN model_providers p ON p.id=m.provider_id WHERE m.id=?',(params['id'],)).fetchone()
        if not row or row[0].casefold()!='openrouter' or row[1]!='external':raise LibraryError('INVALID_PARAMS')
        caps=json.loads(row[2]);caps['authentication']='not_tested'
        action=params['action']
        if action=='save':
            key=params.get('key')
            if not isinstance(key,str) or not 1<=len(key)<=1024 or not key.isascii() or any(ord(c)<33 or ord(c)>126 for c in key):raise LibraryError('INVALID_PARAMS')
            self.vault.write(params['id'],key)
        elif action=='delete':self.vault.delete(params['id'])
        else:
            if params.get('allow_external') is not True:return {'status':'external_consent_required','inferenceCalled':False}
            key=self.vault.read(params['id'])
            if not key:return {'status':'credential_missing','inferenceCalled':False}
            from .providers import metadata
            try:
                data=metadata('https://openrouter.ai/api/v1/key',key=key)
                if not isinstance(data.get('data'),dict):raise ValueError()
                caps['authentication']='authenticated'
            except Exception:caps['authentication']='failed'
        self.db.execute('UPDATE model_registry SET capabilities_json=?,enabled=0 WHERE id=?',(json.dumps(caps),params['id']))
        return {'status':caps['authentication'] if action=='test' else 'saved' if action=='save' else 'deleted','inferenceCalled':False}
