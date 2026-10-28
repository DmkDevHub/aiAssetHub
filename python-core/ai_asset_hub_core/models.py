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
        rows=self.db.execute('''SELECT m.id,p.name,p.kind,m.model_id,m.modalities_json,m.enabled
            FROM model_registry m JOIN model_providers p ON p.id=m.provider_id
            WHERE m.id>? ORDER BY m.id LIMIT 11''',(params.get('after_id') or '',)).fetchall()
        items=[{'id':r[0],'provider':r[1],'kind':r[2],'modelId':r[3],'modalities':json.loads(r[4]),'enabled':bool(r[5])} for r in rows[:10]]
        return {'items':items,'next_cursor':items[-1]['id'] if len(rows)>10 else None}
