"""Cosine ranking over compatible, current stored vectors only."""
from .embeddings import Embeddings,embed,vector
from .libraries import LibraryError
from .libraries import valid_id
import unicodedata


def criteria(value):
    defaults={'library_id':None,'folder_parts':[],'kind':'','tag':'','analysis':'','group_id':None}
    if not isinstance(value,dict) or set(value)-set(defaults):raise LibraryError('INVALID_PARAMS')
    result={**defaults,**value}
    if result['group_id'] is not None and not valid_id(result['group_id']):raise LibraryError('INVALID_PARAMS')
    if result['library_id'] is not None and not valid_id(result['library_id']):raise LibraryError('INVALID_PARAMS')
    parts=result['folder_parts']
    if not isinstance(parts,list) or len(parts)>32 or any(not isinstance(p,str) or not p or len(p)>255 or p in ('.','..') or '/' in p or '\\' in p for p in parts) or parts and not result['library_id']:raise LibraryError('INVALID_PARAMS')
    if any(not isinstance(result[k],str) or len(result[k])>64 for k in ('kind','tag','analysis')) or result['analysis'] not in ('','unanalyzed','completed','failed'):raise LibraryError('INVALID_PARAMS')
    return result


def matches(database,identifier,filters):
    db=database.connection
    row=db.execute('''SELECT a.library_root_id,f.relative_path,f.extension FROM assets a JOIN library_roots l ON l.id=a.library_root_id
        JOIN asset_files f ON f.asset_id=a.id WHERE a.id=? AND l.enabled=1''',(identifier,)).fetchone()
    if not row:return False
    if filters.get('group_id') and not db.execute('SELECT 1 FROM asset_group_members WHERE group_id=? AND asset_id=?',(filters['group_id'],identifier)).fetchone():return False
    if filters['library_id'] and row[0]!=filters['library_id']:return False
    if row[1].replace('\\','/').split('/')[:len(filters['folder_parts'])]!=filters['folder_parts']:return False
    if filters['kind'] and (row[2].lstrip('.').upper() or 'FILE')!=filters['kind']:return False
    if filters['tag']:
        tag=unicodedata.normalize('NFKC',filters['tag']).strip().casefold()
        if not db.execute("SELECT 1 FROM asset_tags at JOIN tags t ON t.id=at.tag_id WHERE at.asset_id=? AND at.source='user' AND t.normalized_label=?",(identifier,tag)).fetchone():return False
    if filters['analysis']:
        from .analysis_state import asset_state
        state=asset_state(db,identifier)
        if filters['analysis']=='completed' and not state['hasActiveResult'] or filters['analysis']=='unanalyzed' and state['hasActiveResult'] or filters['analysis']=='failed' and state['lastAttemptState']!='failed':return False
    return True


def keywords(database,query,filters):
    terms=unicodedata.normalize('NFKC',query).casefold().split();rows=[]
    source=database.connection.execute('''SELECT d.asset_id,d.searchable_text FROM search_documents d JOIN assets a ON a.id=d.asset_id
        JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 LIMIT 10001''').fetchall()
    if len(source)>10000:raise LibraryError('EMBEDDING_LIMIT')
    for identifier,text in source:
        if all(term in text for term in terms) and matches(database,identifier,filters):rows.append((identifier,sum(text.count(term) for term in terms)/max(1,len(text))))
    rows.sort(key=lambda row:(-row[1],row[0]));return [row[0] for row in rows]


def search(database,job,control):
    service=Embeddings(database);profile=job['profile']
    filters=criteria(job.get('criteria',{}));candidates=[(doc,values) for doc,values in service.ready(profile) if matches(database,doc['id'],filters)] if profile else []
    lexical=keywords(database,job['query'],filters) if job['mode']=='hybrid' else []
    def register(connection):
        control['connection']=connection
        if connection.sock:control['socket']=connection.sock
    rows=[]
    if candidates:
        service.fresh(profile);query=vector(embed(profile,job['query'],True,control['cancel'],register),profile['dimension']);service.fresh(profile)
        candidates=[(doc,values) for doc,values in service.ready(profile) if matches(database,doc['id'],filters)]
    for doc,values in candidates:
        score=max(-1.0,min(1.0,sum(a*b for a,b in zip(query,values))))
        rows.append({'id':doc['id'],'score':score,'semanticScore':score,'reason':'semantic'})
    rows.sort(key=lambda row:(-row['score'],row['id']))
    if job['mode']=='semantic':return rows[:50]
    merged={row['id']:{**row,'score':1/(60+rank),'semanticScore':row['score']} for rank,row in enumerate(rows,1)}
    for rank,identifier in enumerate(lexical,1):
        row=merged.setdefault(identifier,{'id':identifier,'score':0,'reason':'keyword','semanticScore':None})
        row['keywordScore']=1/(60+rank);row['score']+=row['keywordScore']
        if row['semanticScore'] is not None:row['reason']='hybrid'
    return sorted(merged.values(),key=lambda row:(-row['score'],row['id']))[:50]
