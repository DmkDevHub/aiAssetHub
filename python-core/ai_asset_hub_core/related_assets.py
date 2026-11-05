"""Recommendations from public indexed metadata and compatible stored vectors only."""
import json
from .collections import Collections
from .catalog_query import CatalogQuery,criteria
from .embeddings import Embeddings
from .asset_management import AssetManagement
from .libraries import LibraryError


class RelatedAssets(Collections):
    def tokens(self,asset):
        tokens=set()
        queries=[('tag',"SELECT tag_id FROM asset_tags WHERE asset_id=? AND source='user'"),
            ('group','SELECT group_id FROM asset_group_members WHERE asset_id=?'),
            ('package','SELECT m.package_id FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id WHERE m.asset_id=? AND p.enabled=1')]
        for axis,sql in queries:
            tokens.update((axis,r[0]) for r in self.db.execute(sql,(asset,)))
        for axis,code in self.db.execute('SELECT axis,code FROM asset_classification_links WHERE asset_id=?',(asset,)):tokens.add((axis,code))
        row=self.db.execute('SELECT primary_code FROM asset_classification_selections WHERE asset_id=?',(asset,)).fetchone()
        if row and row[0]:tokens.add(('type',row[0]))
        tokens.update(('creator',r[0]) for r in CatalogQuery(self.database).creators(asset))
        return tokens

    def query(self,params):
        self.keys(params,'asset_id mode criteria limit');asset=params['asset_id'];self.require_asset(asset)
        mode=params['mode'];limit=params['limit'];filters=criteria(params['criteria'])
        if not isinstance(mode,str) or mode not in ('metadata','stored_vectors','hybrid') or type(limit) is not int or not 1<=limit<=20:raise LibraryError('INVALID_PARAMS')
        catalog=CatalogQuery(self.database);stamp=catalog.stamp();source=self.tokens(asset);service=AssetManagement(self.database)
        connected={l['targetId'] for l in service.relation_value(asset)}
        for identifier,raw in self.db.execute("SELECT asset_id,value_json FROM metadata_decisions WHERE field='relations'"):
            if any(l['targetId']==asset for l in json.loads(raw)):connected.add(identifier)
        rows=self.db.execute('''SELECT a.id,coalesce(u.title_override,a.display_name) FROM assets a JOIN library_roots l ON l.id=a.library_root_id
            LEFT JOIN asset_user_annotations u ON u.asset_id=a.id WHERE l.enabled=1 AND EXISTS(SELECT 1 FROM asset_files f WHERE f.asset_id=a.id AND f.exists_flag=1) ORDER BY a.id LIMIT 10001''').fetchall()
        if len(rows)>10000:raise LibraryError('CATALOG_LIMIT')
        candidates={i:name for i,name in rows if i!=asset and i not in connected and catalog.matches(i,filters)}
        lexical={};reasons={}
        if mode!='stored_vectors':
            for identifier in candidates:
                target=self.tokens(identifier);shared=source&target
                if shared:
                    lexical[identifier]=len(shared)/len(source|target)
                    reasons[identifier]=[dict(kind='shared_'+axis,count=sum(a==axis for a,_ in shared)) for axis in sorted({a for a,_ in shared})]
        semantic={};profile=None;ready=[];vector_status='not-requested'
        if mode!='metadata':
            embeddings=Embeddings(self.database);profile=embeddings.profile()
            ready=embeddings.ready(profile) if profile else []
            current=next((values for doc,values in ready if doc['id']==asset),None)
            vector_status='ready' if current is not None else 'source-vector-unavailable'
            if current is not None:
                for doc,values in ready:
                    if doc['id'] in candidates:
                        score=max(-1.0,min(1.0,sum(a*b for a,b in zip(current,values))))
                        if score>0:semantic[doc['id']]=score
        ranks={}
        for scores in (lexical,semantic):
            for rank,identifier in enumerate(sorted(scores,key=lambda i:(-scores[i],i)),1):ranks[identifier]=ranks.get(identifier,0)+1/(60+rank)
        scored=lexical if mode=='metadata' else semantic if mode=='stored_vectors' else ranks
        items=[]
        for identifier in sorted(scored,key=lambda i:(-scored[i],i))[:limit]:
            evidence=list(reasons.get(identifier,[]))
            if identifier in semantic:evidence.append(dict(kind='stored_vector',profileVersion=profile['version']))
            items.append(dict(id=identifier,name=candidates[identifier][:160],score=scored[identifier],metadataScore=lexical.get(identifier),semanticScore=semantic.get(identifier),
                reasons=evidence,confirmed=False))
        if catalog.stamp()!=stamp:raise LibraryError('METADATA_CONFLICT')
        result=dict(schema='related-assets.v1',assetId=asset,mode=mode,items=items,vectorStatus=vector_status,
            profileVersion=profile['version'] if profile else None,inferenceCalled=False,relationshipCreated=False)
        if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>12000:raise LibraryError('CATALOG_LIMIT')
        return result
