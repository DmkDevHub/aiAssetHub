"""Read projections only. No analysis, embedding, thumbnails or original file writes."""
from .libraries import LibraryError,LibraryService,valid_id
from .search import SearchService
from .semantic_search import criteria,matches
from .analysis_state import asset_state
from .annotations import AnnotationService
from .analysis_results import AssetAnalysis
from pathlib import Path
from .session_file import no_links
from .libraries import _local_path


class McpQueries:
    def __init__(self,database,application=None):self.database=database;self.db=database.connection;self.application=application

    def dispatch(self,name,params):
        actions={'list_libraries':self.libraries,'search_assets':self.search,'get_asset':self.detail,'get_asset_files':self.files,'get_analysis_status':self.status}
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

    def require(self,params,extra=()):
        if not isinstance(params,dict) or set(params)-{'asset_id',*extra} or not valid_id(params.get('asset_id')):raise LibraryError('INVALID_PARAMS')
        if not self.db.execute('SELECT 1 FROM assets a JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1',(params['asset_id'],)).fetchone():raise LibraryError('MCP_ASSET_NOT_FOUND')
        return params['asset_id']

    def detail(self,params):
        identifier=self.require(params,('history_after_id',));history={'asset_id':identifier}
        if params.get('history_after_id') is not None:history['after_id']=params['history_after_id']
        return {**self.summary(identifier),'user':AnnotationService(self.database).get({'asset_id':identifier}),
                'activeResult':AssetAnalysis(self.database).get({'asset_id':identifier})['active'],
                'history':AssetAnalysis(self.database).history(history)}

    def files(self,params):
        identifier=self.require(params);result=[]
        rows=self.db.execute('''SELECT f.id,f.absolute_path,f.relative_path,f.extension,l.absolute_path,o.width,o.height,o.duration_ms
            FROM asset_files f JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id
            LEFT JOIN asset_observations o ON o.asset_file_id=f.id WHERE a.id=? ORDER BY f.id LIMIT 21''',(identifier,)).fetchall()
        if len(rows)>20:raise LibraryError('MCP_SEARCH_LIMIT')
        for row in rows:
            item={'id':row[0],'relativePath':row[2],'kind':row[3].lstrip('.').upper() or 'FILE','availability':'unavailable','previewSupported':row[3].lower() in ('.png','.jpg','.jpeg'),'width':row[5],'height':row[6],'durationMs':row[7]}
            path,root=Path(row[1]),Path(row[4])
            try:
                _local_path(path);_local_path(root);no_links(path);no_links(root)
                if len(str(path))>2048 or not path.is_relative_to(root) or path.relative_to(root).as_posix()!=row[2].replace('\\','/') or not path.resolve(strict=False).is_relative_to(root.resolve(strict=False)):raise ValueError()
                item['path']=str(path)
                try:
                    info=path.stat()
                    if not path.is_file():raise ValueError()
                    item.update(availability='present',size=info.st_size,mtimeNs=str(info.st_mtime_ns))
                except FileNotFoundError:item['availability']='missing'
            except (OSError,ValueError,LibraryError):item.pop('path',None)
            result.append(item)
        return {'assetId':identifier,'files':result,'modelCalled':False}

    def status(self,params):
        if not isinstance(params,dict) or set(params)-{'asset_ids'}:raise LibraryError('INVALID_PARAMS')
        identifiers=params.get('asset_ids');truncated=False
        if identifiers is None:
            rows=self.db.execute('SELECT a.id FROM assets a JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 ORDER BY a.id LIMIT 51').fetchall()
            identifiers=[r[0] for r in rows[:50]];truncated=len(rows)>50
        if not isinstance(identifiers,list) or len(identifiers)>50 or any(not valid_id(i) for i in identifiers) or len(set(identifiers))!=len(identifiers):raise LibraryError('INVALID_PARAMS')
        for identifier in identifiers:self.require({'asset_id':identifier})
        latest=self.db.execute('SELECT id FROM analysis_jobs ORDER BY created_at DESC,rowid DESC LIMIT 1').fetchone();job=None
        if latest:
            from .analysis_jobs import AnalysisJobs
            engine=self.application._analysis if self.application else None
            job=AnalysisJobs(self.database).status({'job_id':latest[0]},bool(engine and engine.active(latest[0])))
        return {'items':[{'id':i,**asset_state(self.db,i)} for i in identifiers],'truncated':truncated,'latestGlobalJob':job,'modelCalled':False}
