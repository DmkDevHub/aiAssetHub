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
        ready=len(self.ready(profile)) if profile else 0
        stored=self.db.execute('SELECT count(*) FROM asset_embeddings WHERE embedding_model=?',(profile['version'],)).fetchone()[0] if profile else 0
        return {'profile':profile,'readyCount':ready,'staleCount':stored-ready,'inferenceCalled':False}

    def documents(self):
        rows=self.db.execute('''SELECT a.id,r.id,r.description,r.tags_json,run.input_fingerprint,a.library_root_id,f.relative_path,f.extension
            FROM asset_active_results ar JOIN assets a ON a.id=ar.asset_id JOIN library_roots l ON l.id=a.library_root_id
            JOIN analysis_results r ON r.id=ar.analysis_result_id JOIN analysis_runs run ON run.id=r.run_id JOIN asset_files f ON f.asset_id=a.id
            WHERE l.enabled=1 AND f.exists_flag=1 AND f.sha256=run.input_fingerprint ORDER BY a.id LIMIT 10001''').fetchall()
        if len(rows)>10000:raise LibraryError('EMBEDDING_LIMIT')
        result={}
        for r in rows:
            public=self.db.execute('SELECT searchable_text FROM catalog_search_projection WHERE asset_id=?',(r[0],)).fetchone()
            text=r[2]+'\n'+' '.join(json.loads(r[3]))+'\n'+(public[0] if public else '')
            if len(text.encode('utf-8'))>24000:continue
            fingerprint=hashlib.sha256(json.dumps((r[1],text,r[4]),ensure_ascii=False).encode()).hexdigest()
            result[r[0]]={'id':r[0],'resultId':r[1],'text':text,'fingerprint':fingerprint,'libraryId':r[5],'relativePath':r[6],'kind':r[7].lstrip('.').upper()}
        return result

    def ready(self,profile):
        documents=self.documents();result=[]
        for identifier,result_id,dimension,blob,fingerprint in self.db.execute('SELECT asset_id,result_id,dimension,vector_blob,input_fingerprint FROM asset_embeddings WHERE embedding_model=?',(profile['version'],)):
            doc=documents.get(identifier)
            if not doc or doc['resultId']!=result_id or doc['fingerprint']!=fingerprint:continue
            if dimension!=profile['dimension'] or len(blob)!=dimension*4:continue
            try:values=vector(list(struct.unpack('<'+'f'*dimension,blob)),dimension)
            except (ValueError,LibraryError,struct.error):continue
            result.append((doc,values))
        return result

    def fresh(self,profile):
        if self.profile()!=profile:raise LibraryError('EMBEDDING_PROFILE_CHANGED')
        dimension,revision=inspect(profile['modelName'])
        if dimension!=profile['dimension'] or revision!=profile['metadataVersion']:raise LibraryError('EMBEDDING_PROFILE_CHANGED')


def embed(profile,text,query,cancel,register):
    import http.client
    if cancel.is_set():raise LibraryError('USER_CANCELED')
    if not isinstance(text,str) or len(text.encode('utf-8'))>24000:raise LibraryError('EMBEDDING_LIMIT')
    prefix=('task: search result | query: ' if query else 'title: none | text: ') if profile['prefixScheme']=='embeddinggemma' else ''
    connection=http.client.HTTPConnection('127.0.0.1',11434,timeout=3);register(connection)
    try:
        connection.connect();connection.auto_open=0;register(connection)
        if cancel.is_set():raise LibraryError('USER_CANCELED')
        connection.sock.settimeout(120)
        connection.request('POST','/api/embed',json.dumps({'model':profile['modelName'],'input':prefix+text,'truncate':False,'keep_alive':'0','options':{'num_gpu':0,'num_thread':2}}).encode(),{'Content-Type':'application/json'})
        response=connection.getresponse();raw=response.read(2_000_001)
        if response.status!=200 or len(raw)>2_000_000:raise LibraryError('EMBEDDING_FAILED')
        data=json.loads(raw)
        if data.get('model')!=profile['modelName'] or not isinstance(data.get('embeddings'),list) or len(data['embeddings'])!=1:raise LibraryError('EMBEDDING_INVALID_VECTOR')
        if cancel.is_set():raise LibraryError('USER_CANCELED')
        return vector(data['embeddings'][0],profile['dimension'])
    except LibraryError:raise
    except Exception:raise LibraryError('USER_CANCELED' if cancel.is_set() else 'EMBEDDING_FAILED') from None
    finally:connection.close()
