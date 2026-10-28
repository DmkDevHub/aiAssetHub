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
        if not isinstance(selected,list) or len(selected)>200 or not all(valid_id(i) for i in selected) or len(set(selected))!=len(selected):raise LibraryError('INVALID_PARAMS')
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

    def preview(self, params, internal=False):
        from .models import ModelService
        from .model_policy import BudgetPolicy,money
        from .analysis_input import source_info
        from decimal import Decimal
        targets=self.targets(params)
        checked=ModelService(self.database).validate({'id':params['model_id'],'modality':'image'})
        if not checked['compatible']:raise LibraryError(checked['reason'])
        snapshot=checked['snapshot'];cost=Decimal('0')
        if snapshot['kind']=='external' and snapshot['inspection'].get('costClass')=='paid':
            caps=snapshot['inspection'];pricing=caps.get('pricing',{});context=caps.get('contextLength')
            if type(context) is not int or not 1<=context<=2_000_000 or any(Decimal(value)!=0 for key,value in pricing.items() if key not in ('prompt','completion','image','request')):raise LibraryError('COST_ESTIMATE_UNAVAILABLE')
            cost=(Decimal(pricing['prompt'])*context+Decimal(pricing['completion'])*512+Decimal(pricing.get('image','0'))+Decimal(pricing.get('request','0')))*len(targets)
        manager=BudgetPolicy(self.db)
        if targets:manager.check(params['model_id'],str(cost),len(targets))
        live=[]
        for row in targets:
            try:
                path,info=source_info(self.database,row[0]);live.append((row[0],info.st_size,info.st_mtime_ns,'present'))
            except LibraryError as error:live.append((row[0],None,None,str(error)))
        snapshot['analysisLimits']={'outputTokens':512,'inputBytes':20_000_000,'imageEdge':512,'promptSchema':'asset-description.v1'}
        token=hashlib.sha256(json.dumps({'request':params,'targets':live,'model':snapshot['profileVersion'],'cost':str(cost)},sort_keys=True).encode('utf-8')).hexdigest()
        response={'targetCount':len(targets),'missingCount':sum(row[3]!='present' for row in live),'planToken':token,
                'estimatedUpperBoundUsd':str(cost),'costIsEstimate':True,'externalTransfer':snapshot['kind']=='external',
                'paid':snapshot['inspection'].get('costClass')=='paid','snapshot':snapshot,'inferenceCalled':False}
        if internal:response['_inputVersions']={row[0]:{'size':row[1],'mtimeNs':row[2],'status':row[3]} for row in live}
        return response
