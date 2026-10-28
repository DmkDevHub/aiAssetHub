"""Cosine ranking over compatible, current stored vectors only."""
from .embeddings import Embeddings,embed,vector
from .libraries import LibraryError


def search(database,job,control):
    service=Embeddings(database);profile=job['profile']
    if not profile or not service.ready(profile):raise LibraryError('EMBEDDING_NOT_READY')
    service.fresh(profile)
    def register(connection):
        control['connection']=connection
        if connection.sock:control['socket']=connection.sock
    query=vector(embed(profile,job['query'],True,control['cancel'],register),profile['dimension'])
    service.fresh(profile);rows=[]
    for doc,values in service.ready(profile):
        score=max(-1.0,min(1.0,sum(a*b for a,b in zip(query,values))))
        rows.append({'id':doc['id'],'score':score,'semanticScore':score,'reason':'semantic'})
    rows.sort(key=lambda row:(-row['score'],row['id']))
    return rows[:50]
