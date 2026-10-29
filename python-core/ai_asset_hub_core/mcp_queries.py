"""Read projections only. No analysis, embedding, thumbnails or original file writes."""
from .libraries import LibraryError,LibraryService,valid_id
from .search import SearchService
from .semantic_search import criteria,matches
from .analysis_state import asset_state
from .annotations import AnnotationService
from .analysis_results import AssetAnalysis


class McpQueries:
    def __init__(self,database):self.database=database;self.db=database.connection

    def dispatch(self,name,params):
        actions={'list_libraries':self.libraries,'search_assets':self.search}
        if name not in actions:raise LibraryError('MCP_TOOL_NOT_ALLOWED')
        return actions[name](params)

    def libraries(self,params):
        result=LibraryService(self.database).list(params)
        return {'items':result['libraries'],'next_cursor':result['next_cursor']}

    def summary(self,identifier):
        row=self.db.execute('''SELECT a.id,coalesce(u.title_override,a.display_name),a.library_root_id,f.relative_path,f.extension,f.exists_flag
            FROM assets a JOIN asset_files f ON f.asset_id=a.id JOIN library_roots l ON l.id=a.library_root_id
            LEFT JOIN asset_user_annotations u ON u.asset_id=a.id WHERE a.id=? AND l.enabled=1''',(identifier,)).fetchone()
        if not row:raise LibraryError('MCP_ASSET_NOT_FOUND')
        active=AssetAnalysis(self.database).get({'asset_id':identifier})['active']
        user=AnnotationService(self.database).get({'asset_id':identifier})
        return {'id':row[0],'name':row[1],'libraryId':row[2],'relativePath':row[3],'kind':row[4].lstrip('.').upper() or 'FILE',
                'indexedExists':bool(row[5]),'description':active['description'][:512] if active else user['description'][:512],
                'descriptionSource':'ai' if active else 'user','analysis':asset_state(self.db,identifier)}

    def search(self,params):
        if not isinstance(params,dict) or set(params)-{'query','filters','limit','after_id','mode'} or params.get('mode','keyword')!='keyword':raise LibraryError('INVALID_PARAMS')
        query=params.get('query');limit=params.get('limit',10);cursor=params.get('after_id')
        if not isinstance(query,str) or len(query)>256 or type(limit) is not int or not 1<=limit<=20 or cursor is not None and not valid_id(cursor):raise LibraryError('INVALID_PARAMS')
        filters=criteria(params.get('filters',{}));result=[];examined=0
        while True:
            if query.strip():page=SearchService(self.database).search({'query':query,'after_id':cursor});ids=page['ids'];next_page=page['next_cursor']
            else:
                rows=self.db.execute('''SELECT a.id FROM assets a JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 AND a.id>? ORDER BY a.id LIMIT 201''',(cursor or '',)).fetchall()
                ids=[r[0] for r in rows[:200]];next_page=ids[-1] if len(rows)>200 else None
            for identifier in ids:
                examined+=1
                if examined>10000:raise LibraryError('MCP_SEARCH_LIMIT')
                if matches(self.database,identifier,filters):
                    if len(result)==limit:return {'items':result,'next_cursor':result[-1]['id'],'mode':'keyword','modelCalled':False}
                    result.append(self.summary(identifier))
            if not next_page:return {'items':result,'next_cursor':None,'mode':'keyword','modelCalled':False}
            cursor=next_page
