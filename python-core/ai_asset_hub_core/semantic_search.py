"""Cosine ranking over compatible, current stored vectors only."""
from .embeddings import Embeddings,embed,vector
from .libraries import LibraryError
from .libraries import valid_id
import unicodedata


def criteria(value):
    from .catalog_query import criteria as validate
    return validate(value)


def matches(database,identifier,filters):
    from .catalog_query import CatalogQuery
    return CatalogQuery(database).matches(identifier,filters)


def keywords(database,query,filters):
    terms=unicodedata.normalize('NFKC',query).casefold().split();rows=[]
    source=database.connection.execute('''SELECT d.asset_id,d.searchable_text FROM catalog_documents d JOIN assets a ON a.id=d.asset_id
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
