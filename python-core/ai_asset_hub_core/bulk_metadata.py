"""Pure bulk metadata plans. Preview never writes DB/files or invokes a model."""
import copy
import json
from .analysis_contract import digest
from .annotations import AnnotationService
from .catalog import Catalog
from .collections import Collections
from .creators import Creators
from .provenance import Provenance
from .source_records import Sources
from .packages import Packages
from .asset_management import AssetManagement
from .libraries import LibraryError,valid_id
from .metadata_values import MetadataError
from .taxonomy import TaxonomyError

FIELDS=frozenset(('groups','classification','creators','sources','tags','basic','packages','relations'))


def bounded(value):
    if len(json.dumps(value,ensure_ascii=False).encode('utf-8'))>12000:raise LibraryError('BULK_LIMIT')
    return value


def identifiers(value,limit=32):
    if not isinstance(value,list) or len(value)>limit or any(not valid_id(v) for v in value) or len(set(value))!=len(value):raise LibraryError('INVALID_PARAMS')
    return sorted(value)


def edit_set(before,change,normalize,limit):
    if not isinstance(change,dict) or set(change) not in ({'set'},{'add','remove'}):raise LibraryError('INVALID_PARAMS')
    if 'set' in change:return normalize(change['set'])
    add,remove=normalize(change['add']),normalize(change['remove'])
    key=lambda v:json.dumps(v,sort_keys=True,ensure_ascii=False)
    if {key(v) for v in add}&{key(v) for v in remove}:raise LibraryError('INVALID_PARAMS')
    result={key(v):v for v in before if key(v) not in {key(r) for r in remove}}
    result.update({key(v):v for v in add})
    if len(result)>limit:raise LibraryError('BULK_LIMIT')
    return sorted(result.values(),key=key)


class BulkMetadata(Catalog):
    def validate_relations(self,updates):
        graph={};values={r[0]:json.loads(r[1]) for r in self.db.execute("SELECT asset_id,value_json FROM metadata_decisions WHERE field='relations'")};values.update(updates)
        for asset,links in values.items():
            for link in links:
                if link['kind']=='related':continue
                child,parent=(link['targetId'],asset) if link['kind']=='original_of' else (asset,link['targetId'])
                graph.setdefault(child,set()).add(parent)
        nodes=set(graph)|{p for parents in graph.values() for p in parents};degree={node:0 for node in nodes}
        for parents in graph.values():
            for parent in parents:degree[parent]+=1
        pending=[node for node in nodes if not degree[node]];count=0
        while pending:
            node=pending.pop();count+=1
            for parent in graph.get(node,()):
                degree[parent]-=1
                if not degree[parent]:pending.append(parent)
        if count!=len(nodes):raise LibraryError('INVALID_PARAMS')

    def read_field(self,asset,field):
        if field=='basic':
            state=AnnotationService(self.database).get({'asset_id':asset})
            return {key:state[key] for key in ('title','description','aliases')},state['revision'],[]
        if field=='packages':
            state=self.membership_value(asset,'package')
            refs=[list(r) for r in self.db.execute('SELECT p.id,p.revision,p.enabled FROM asset_packages p JOIN asset_package_members m ON m.package_id=p.id WHERE m.asset_id=? ORDER BY p.id',(asset,))]
            return state['ids'],state['revision'],refs
        if field=='relations':
            state=AssetManagement(self.database).relations({'asset_id':asset})
            # Bind the whole existing graph so edits on other assets cannot make a reviewed graph cyclic.
            refs=[list(r) for r in self.db.execute("SELECT asset_id,value_json,revision FROM metadata_decisions WHERE field='relations' ORDER BY asset_id")]
            return state['value'],state['revision'],refs
        if field=='groups':
            state=self.membership_value(asset);return state['ids'],state['revision'],[self.group(i) for i in state['ids']]
        if field=='classification':
            state=self.classification({'asset_id':asset})
            resources=[list(r) for r in self.db.execute('SELECT version,kind,payload_json FROM classification_dictionaries ORDER BY version')]
            return state['value'],state['revision'],resources
        if field=='tags':
            state=AnnotationService(self.database).get({'asset_id':asset})
            return state['tags'],state['tagsRevision'],[list(r) for r in self.db.execute('SELECT id,label,normalized_label,enabled FROM tags ORDER BY id')]
        if field=='creators':
            service=Provenance(self.database);state=service.links_value({'kind':'asset','id':asset})
            return state['links'],state['revision'],[Creators.public(service.creator(i['creator_id'])) for i in state['links']]
        if field=='sources':
            service=Sources(self.database)
            records=[service.record(r[0]) for r in self.db.execute('SELECT id FROM provenance_sources WHERE asset_id=? AND enabled=1 ORDER BY id',(asset,))]
            if len(records)>16:raise LibraryError('BULK_LIMIT')
            public=[{'id':r['id'],**service.public_value(r['value'])} for r in records]
            return public,digest([{k:r[k] for k in ('id','revision','enabled')} for r in records]),records
        raise LibraryError('INVALID_PARAMS')

    def next_value(self,asset,field,before,change):
        resources=[]
        if field=='basic':
            self.keys(change,'title description aliases')
            after={'title':AssetManagement.text(change['title'],128),'description':AssetManagement.text(change['description'],1024),'aliases':AnnotationService.aliases(change['aliases'])}
        elif field=='packages':
            after=edit_set(before,change,lambda ids:identifiers(ids,16),16)
            resources=[{key:value[key] for key in ('id','revision')} for value in (Packages(self.database).package(i) for i in after)]
        elif field=='relations':
            if not isinstance(change,list) or len(change)>16:raise LibraryError('INVALID_PARAMS')
            seen=set();after=[]
            for item in change:
                self.keys(item,'targetId kind')
                if not valid_id(item['targetId']) or item['targetId']==asset or item['kind'] not in ('related','original_of','variant_of','derived_from'):raise LibraryError('INVALID_PARAMS')
                pair=(item['targetId'],item['kind'])
                if pair in seen:raise LibraryError('INVALID_PARAMS')
                seen.add(pair);self.require_asset(item['targetId']);after.append(dict(item))
                resources.append([item['targetId'],True])
        elif field=='groups':
            after=edit_set(before,change,identifiers,32)
            resources=[self.group(i) for i in after]
        elif field=='tags':
            def labels(items):return sorted(AnnotationService.labels(items).values(),key=str.casefold)
            # Compare tags by their normalized dictionary identity, not display case.
            if not isinstance(change,dict) or set(change) not in ({'set'},{'add','remove'}):raise LibraryError('INVALID_PARAMS')
            if 'set' in change:after=labels(change['set'])
            else:
                add,remove=AnnotationService.labels(change['add']),AnnotationService.labels(change['remove'])
                if set(add)&set(remove):raise LibraryError('INVALID_PARAMS')
                values={v.casefold():v for v in before if v.casefold() not in remove};values.update(add);after=sorted(values.values(),key=str.casefold)
            if len(after)>32 or sum(map(len,after))>512:raise LibraryError('BULK_LIMIT')
            for value in after:
                row=self.db.execute('SELECT enabled FROM tags WHERE normalized_label=?',(value.casefold(),)).fetchone()
                if row and not row[0] and value.casefold() not in {v.casefold() for v in before}:raise LibraryError('INVALID_PARAMS')
            after=sorted([self.db.execute('SELECT label FROM tags WHERE normalized_label=?',(v.casefold(),)).fetchone()[0]
                if self.db.execute('SELECT 1 FROM tags WHERE normalized_label=?',(v.casefold(),)).fetchone() else v for v in after],key=str.casefold)
        elif field=='classification':
            if not isinstance(change,dict) or not change or set(change)-{'primary','navigation','facets','type_version','facet_version'}:raise LibraryError('INVALID_PARAMS')
            after=copy.deepcopy(before);after.update(change)
            if any(not isinstance(after[k],str) or not 1<=len(after[k])<=128 for k in ('type_version','facet_version')):raise LibraryError('INVALID_PARAMS')
            try:
                types=self.metadata.dictionary(after['type_version'],'type');facets=self.metadata.dictionary(after['facet_version'],'facet')
                assigned=types.assignment(after['primary'],after['navigation'],version=types.version)
                axes=facets.assignment(after['facets'],version=facets.version)
                after.update(primary=assigned['primary'],navigation=assigned['navigation'],facets=axes['values'])
                if all(after[k]==before[k] for k in ('primary','navigation','type_version','facet_version')) and facets.assignment(before['facets'],version=facets.version)==axes:after=copy.deepcopy(before)
            except (MetadataError,TaxonomyError,TypeError):raise LibraryError('INVALID_PARAMS') from None
        elif field=='creators':
            service=Provenance(self.database)
            def links(items):
                if not isinstance(items,list) or len(items)>16:raise LibraryError('INVALID_PARAMS')
                result=[]
                for item in items:
                    self.keys(item,'creator_id role')
                    if not valid_id(item['creator_id']) or item['role'] not in ('creator','producer','distributor'):raise LibraryError('INVALID_PARAMS')
                    result.append(dict(item))
                if len({(v['creator_id'],v['role']) for v in result})!=len(result):raise LibraryError('INVALID_PARAMS')
                return sorted(result,key=lambda v:(v['creator_id'],v['role']))
            after=edit_set(before,change,links,16)
            for item in after:
                creator=service.creator(item['creator_id'])
                if not creator['enabled'] and item not in before:raise LibraryError('INVALID_PARAMS')
                resources.append(Creators.public(creator))
        elif field=='sources':
            if not isinstance(change,dict) or set(change) not in ({'append'},{'records'}):raise LibraryError('INVALID_PARAMS')
            values=change.get('append',change.get('records'))
            if not isinstance(values,list) or len(values)>(8 if 'append' in change else 16):raise LibraryError('BULK_LIMIT')
            after=copy.deepcopy(before)
            seen=set()
            for value in values:
                self.keys(value,'site productName' if 'append' in change else 'id site productName')
                public={'site':self.text(value['site'],128),'productName':self.text(value['productName'],256)}
                if 'records' in change:
                    if not valid_id(value['id']) or value['id'] in seen:raise LibraryError('INVALID_PARAMS')
                    seen.add(value['id'])
                    found=next((r for r in after if r.get('id')==value['id']),None)
                    if found is None:raise LibraryError('INVALID_PARAMS')
                    found.update(public)
                elif not any(all(r[k]==v for k,v in public.items()) for r in after):after.append({**public,'new':True})
            if len(after)>16:raise LibraryError('BULK_LIMIT')
        else:raise LibraryError('INVALID_PARAMS')
        return after,resources

    def targets(self,request,check_graph=True):
        if not isinstance(request,dict) or set(request)-{'asset_ids','changes','expected'} or not {'asset_ids','changes'}<=set(request):raise LibraryError('INVALID_PARAMS')
        assets=identifiers(request['asset_ids'],100)
        changes=request['changes'];expected=request.get('expected',{})
        if not assets or not isinstance(changes,dict) or not changes or set(changes)-FIELDS or not isinstance(expected,dict) or set(expected)-set(assets):raise LibraryError('INVALID_PARAMS')
        for versions in expected.values():
            if not isinstance(versions,dict) or set(versions)-set(changes) or any(type(v) is not int or v<0 for f,v in versions.items() if f!='sources') or any(not isinstance(v,str) or len(v)!=64 for f,v in versions.items() if f=='sources'):raise LibraryError('INVALID_PARAMS')
        targets=[];snapshots=[]
        for asset in assets:
            self.require_asset(asset);before={};after={};versions={};resources=[];conflicts=[]
            for field,change in sorted(changes.items()):
                old,version,refs=self.read_field(asset,field);new,new_refs=self.next_value(asset,field,old,change)
                before[field]=old;after[field]=new;versions[field]=version;resources.extend(refs+new_refs)
                if field in expected.get(asset,{}) and expected[asset][field]!=version:conflicts.append(field)
            identity=list(self.db.execute('SELECT updated_at FROM assets WHERE id=?',(asset,)).fetchone())
            files=[list(r) for r in self.db.execute('SELECT id,size_bytes,mtime_ns,exists_flag,sha256 FROM asset_files WHERE asset_id=? ORDER BY id',(asset,))]
            active=self.db.execute('SELECT analysis_result_id FROM asset_active_results WHERE asset_id=?',(asset,)).fetchone()
            attempt=self.db.execute('SELECT id,status FROM analysis_runs WHERE asset_id=? ORDER BY rowid DESC LIMIT 1',(asset,)).fetchone()
            target={'assetId':asset,'before':before,'after':after,'versions':versions,'conflicts':conflicts,'changed':before!=after}
            targets.append(target);snapshots.append([target,resources,identity,files,list(active or []),list(attempt or [])])
        if check_graph:self.validate_relations({t['assetId']:t['after']['relations'] for t in targets if 'relations' in t['after']})
        return targets,digest({'request':request,'snapshots':snapshots,'policy':'bulk-metadata.v1'})

    def preview(self,params):
        self.keys(params,'request after_id plan_token')
        # A deferred read transaction gives all pages a coherent, read-only snapshot.
        self.db.execute('BEGIN')
        try:
            targets,token=self.targets(params['request'])
            if params['plan_token'] is not None and params['plan_token']!=token:raise LibraryError('METADATA_CONFLICT')
            cursor=params['after_id']
            if cursor is not None and cursor not in [r['assetId'] for r in targets]:raise LibraryError('INVALID_PARAMS')
            rows=[r for r in targets if cursor is None or r['assetId']>cursor]
            result=bounded({'items':rows[:1],'next_cursor':rows[0]['assetId'] if len(rows)>1 else None,'planToken':token,
                'targetCount':len(targets),'changedCount':sum(t['changed'] for t in targets),'conflictCount':sum(bool(t['conflicts']) for t in targets),
                'policy':'all-or-nothing','inferenceCalled':False})
            self.db.execute('COMMIT');return result
        except Exception:self.db.execute('ROLLBACK');raise

    def apply_target(self,target):
        asset=target['assetId'];versions=target['versions']
        for field,after in target['after'].items():
            before=target['before'][field]
            if before==after:continue
            if field=='basic':AnnotationService(self.database).save({'asset_id':asset,**after,'expected_revision':versions[field]})
            elif field=='packages':Packages(self.database).package_assign({'asset_id':asset,'package_ids':after,'expected_revision':versions[field]})
            elif field=='relations':self.metadata._decide(asset,'relations','set',versions[field],True,after,None)
            elif field=='groups':self.group_assign({'asset_id':asset,'group_ids':after,'expected_revision':versions[field]})
            elif field=='classification':self.save_classification({'asset_id':asset,'value':after,'expected_revision':versions[field],'confirmed':True})
            elif field=='tags':
                old={v.casefold() for v in before};new={v.casefold() for v in after}
                AnnotationService(self.database).tags({'asset_id':asset,'add':[v for v in after if v.casefold() not in old],
                    'remove':[v for v in before if v.casefold() not in new],'expected_revision':versions[field]})
            elif field=='creators':Provenance(self.database).save_links({'subject':{'kind':'asset','id':asset},'links':after,'expected_revision':versions[field]})
            elif field=='sources':
                service=Sources(self.database)
                for item in after:
                    public={key:item[key] for key in ('site','productName')}
                    if item.get('new'):
                        value={**public,'originalUrl':'','productUrl':'','downloadUrl':'','purchase':{'amount':None,'currency':'','purchasedOn':'','downloadedOn':''}}
                        service.create_record({'subject':{'kind':'asset','id':asset},'value':value})
                    elif item not in before:
                        record=service.record(item['id']);value={**record['value'],**public}
                        service.update_record({'record_id':item['id'],'value':value,'expected_revision':record['revision']})

    def apply(self,params):
        self.keys(params,'request plan_token confirmed')
        if params['confirmed'] is not True or not isinstance(params['plan_token'],str) or len(params['plan_token'])!=64:raise LibraryError('INVALID_PARAMS')
        def operation():
            targets,token=self.targets(params['request'])
            if token!=params['plan_token'] or any(t['conflicts'] for t in targets):raise LibraryError('METADATA_CONFLICT')
            changed=[t for t in targets if t['changed']]
            for target in changed:self.apply_target(target)
            self.validate_relations({})
            if changed:
                from uuid import uuid4
                self.db.execute("INSERT INTO audit_events VALUES (?,'user','bulk.apply','metadata',NULL,'succeeded',strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",
                    (str(uuid4()),json.dumps({'assetIds':[t['assetId'] for t in changed],'fields':sorted(params['request']['changes']),'policy':'all-or-nothing'})))
            return {'updated':len(changed),'unchanged':len(targets)-len(changed),'policy':'all-or-nothing','inferenceCalled':False}
        return self.transaction(operation)
