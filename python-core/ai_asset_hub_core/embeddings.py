"""Versioned local embedding profiles. Configuration/status never embed text."""
import hashlib
import json
import math
import struct
from .libraries import LibraryError
from .providers import metadata


def vector(value,dimension):
    if not isinstance(value,list) or len(value)!=dimension or any(type(n) not in (int,float) or not math.isfinite(n) for n in value):raise LibraryError('EMBEDDING_INVALID_VECTOR')
    norm=math.sqrt(sum(n*n for n in value))
    if not math.isfinite(norm) or norm<1e-12:raise LibraryError('EMBEDDING_INVALID_VECTOR')
    return [n/norm for n in value]


def inspect(model):
    if not isinstance(model,str) or not 1<=len(model)<=160 or any(ord(c)<33 for c in model) or model.endswith(':cloud'):raise LibraryError('INVALID_PARAMS')
    data=metadata('http://127.0.0.1:11434/api/show',{'model':model})
    if 'embedding' not in data.get('capabilities',[]) or data.get('remote_host') or data.get('remote_model'):raise LibraryError('EMBEDDING_MODEL_UNAVAILABLE')
    dimensions={v for k,v in data.get('model_info',{}).items() if k.endswith('.embedding_length') and type(v) is int and 1<=v<=8192}
    if len(dimensions)!=1:raise LibraryError('EMBEDDING_INVALID_VECTOR')
    return dimensions.pop(),hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


class Embeddings:
    def __init__(self,database):self.database=database;self.db=database.connection

    def profile(self):
        row=self.db.execute("SELECT value_json FROM settings WHERE key='embedding.profile'").fetchone()
        return json.loads(row[0]) if row else None

    def configure(self,params):
        if not isinstance(params,dict) or set(params)!={'model_name','prefix_scheme'} or params['prefix_scheme'] not in ('plain','embeddinggemma'):raise LibraryError('INVALID_PARAMS')
        try:dimension,revision=inspect(params['model_name'])
        except LibraryError:raise
        except Exception:raise LibraryError('EMBEDDING_MODEL_UNAVAILABLE') from None
        profile={'modelName':params['model_name'],'dimension':dimension,'metadataVersion':revision,'prefixScheme':params['prefix_scheme'],'formatVersion':1}
        profile['version']=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
        self.db.execute("INSERT INTO settings VALUES ('embedding.profile',?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",(json.dumps(profile),))
        return {'profile':profile,'inferenceCalled':False}

    def status(self,params):
        if params!={}:raise LibraryError('INVALID_PARAMS')
        profile=self.profile()
        return {'profile':profile,'readyCount':0 if not profile else self.db.execute('SELECT count(*) FROM asset_embeddings WHERE embedding_model=? AND dimension=?',(profile['version'],profile['dimension'])).fetchone()[0],'inferenceCalled':False}
