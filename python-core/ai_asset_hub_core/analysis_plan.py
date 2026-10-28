"""Read-only target previews. A preview never creates work or invokes a model."""
import hashlib
import json
from .analysis_state import asset_state
from .libraries import LibraryError, valid_id


class AnalysisPlan:
    def __init__(self, database):
        self.database=database;self.db=database.connection

    def targets(self, params):
        if not isinstance(params,dict) or set(params)!={'mode','scope','library_id','folder_parts','selected_ids','model_id'}:
            raise LibraryError('INVALID_PARAMS')
        if params['mode'] not in ('all','unanalyzed','completed','failed','selected') or params['scope'] not in ('all','library','folder') or not valid_id(params['model_id']):
            raise LibraryError('INVALID_PARAMS')
        selected=params['selected_ids']
        if not isinstance(selected,list) or len(selected)>1000 or not all(valid_id(i) for i in selected) or len(set(selected))!=len(selected):raise LibraryError('INVALID_PARAMS')
        parts=params['folder_parts']
        if not isinstance(parts,list) or len(parts)>32 or any(not isinstance(part,str) or not part or len(part)>255 or part in ('.','..') or '/' in part or '\\' in part for part in parts):raise LibraryError('INVALID_PARAMS')
        if params['scope']=='all':
            if params['library_id'] is not None or parts:raise LibraryError('INVALID_PARAMS')
        else:
            if not valid_id(params['library_id']) or params['scope']=='library' and parts:raise LibraryError('INVALID_PARAMS')
            if not self.db.execute('SELECT 1 FROM library_roots WHERE id=? AND enabled=1',(params['library_id'],)).fetchone():raise LibraryError('LIBRARY_NOT_FOUND')
        if selected:
            valid={r[0] for r in self.db.execute('SELECT a.id FROM assets a JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 AND a.id IN ('+','.join('?' for _ in selected)+')',selected)}
            if valid!=set(selected):raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute('''SELECT a.id,a.library_root_id,f.relative_path,f.size_bytes,f.mtime_ns,f.exists_flag
            FROM assets a JOIN library_roots l ON l.id=a.library_root_id JOIN asset_files f ON f.asset_id=a.id WHERE l.enabled=1 ORDER BY a.id''')
        result=[]
        for row in rows:
            if params['scope']!='all' and row[1]!=params['library_id']:continue
            if params['scope']=='folder' and row[2].replace('\\','/').split('/')[:len(parts)]!=parts:continue
            identifier=row[0];state=asset_state(self.db,identifier)
            mode=params['mode']
            match=mode=='all' or mode=='selected' and identifier in selected or mode=='unanalyzed' and not state['hasActiveResult'] or mode=='completed' and state['hasActiveResult'] or mode=='failed' and state['lastAttemptState']=='failed'
            if match:
                result.append(row)
                if len(result)>1000:raise LibraryError('ANALYSIS_TARGET_LIMIT')
        if len(result)>1000:raise LibraryError('ANALYSIS_TARGET_LIMIT')
        return result

    def preview(self, params):
        targets=self.targets(params)
        token=hashlib.sha256(json.dumps({'request':params,'targets':targets},sort_keys=True).encode('utf-8')).hexdigest()
        return {'targetCount':len(targets),'missingCount':sum(not row[5] for row in targets),'planToken':token,'inferenceCalled':False}
