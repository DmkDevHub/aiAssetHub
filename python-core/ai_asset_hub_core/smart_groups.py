"""Versioned saved predicates over the existing catalog. Evaluation is read-only."""
import json
import base64
import hashlib
from uuid import uuid4
from .collections import Collections
from .catalog_query import CatalogQuery,criteria,normalized,SORTS,UNKNOWN
from .libraries import LibraryError,valid_id

SCHEMA='smart-group.v1'
KEY='catalog.smart-groups.v1'


class SmartGroups(Collections):
    def state(self):
        row=self.db.execute('SELECT value_json FROM settings WHERE key=?',(KEY,)).fetchone()
        return json.loads(row[0]) if row else dict(schema=SCHEMA,revision=0,groups={})

    def references(self,f):
        for key,table,flag in [('group_ids','asset_groups',''),('package_ids','asset_packages',' AND enabled=1'),
            ('creator_ids','creators',' AND deleted=0'),('tags','tags',' AND enabled=1')]:
            for value in f[key]:
                if value!=UNKNOWN and not self.db.execute('SELECT 1 FROM '+table+' WHERE id=?'+flag,(value,)).fetchone():raise LibraryError('INVALID_PARAMS')
        if f['library_id'] and not self.db.execute('SELECT 1 FROM library_roots WHERE id=? AND enabled=1',(f['library_id'],)).fetchone():raise LibraryError('INVALID_PARAMS')
        for key,axis in [('types','type'),('roles','role'),('styles','style'),('genres','genre'),('views','view'),('dimensions','dimension'),('engines','engine')]:
            for code in f[key]:
                if code!=UNKNOWN and not self.db.execute('SELECT 1 FROM classification_terms WHERE axis=? AND code=?',(axis,code)).fetchone():raise LibraryError('INVALID_PARAMS')

    def definition(self,value):
        self.keys(value,'schema query criteria include_groups')
        if value['schema']!=SCHEMA or not isinstance(value['query'],str) or len(value['query'])>256 or len(value['query'].split())>16:raise LibraryError('INVALID_PARAMS')
        f=criteria(value['criteria']);self.references(f)
        refs=value['include_groups']
        if not isinstance(refs,list) or len(refs)>8 or any(not valid_id(i) for i in refs) or len(set(refs))!=len(refs):raise LibraryError('INVALID_PARAMS')
        result=dict(schema=SCHEMA,query=value['query'],criteria=value['criteria'],include_groups=sorted(refs))
        if len(json.dumps(result,ensure_ascii=False).encode())>6000:raise LibraryError('CATALOG_LIMIT')
        return result

    def graph(self,groups):
        order=[];done=set();depth={}
        def visit(identifier,trail):
            if identifier in trail or identifier not in groups:raise LibraryError('INVALID_PARAMS')
            if identifier in done:return
            for ref in groups[identifier]['definition']['include_groups']:visit(ref,trail|{identifier})
            depth[identifier]=1+max((depth[r] for r in groups[identifier]['definition']['include_groups']),default=0)
            if depth[identifier]>8:raise LibraryError('INVALID_PARAMS')
            done.add(identifier);order.append(identifier)
        for identifier in groups:visit(identifier,set())
        return order

    def item(self,state,identifier):
        if not valid_id(identifier) or identifier not in state['groups']:raise LibraryError('INVALID_PARAMS')
        return state['groups'][identifier]

    def list(self,params):
        self.keys(params,'after_id');cursor=params['after_id']
        if cursor is not None and not valid_id(cursor):raise LibraryError('INVALID_PARAMS')
        rows=[r for i,r in sorted(self.state()['groups'].items()) if cursor is None or i>cursor]
        return dict(items=[{k:r[k] for k in ('id','name','revision')} for r in rows[:10]],next_cursor=rows[9]['id'] if len(rows)>10 else None)

    def get(self,params):
        self.keys(params,'group_id');return self.item(self.state(),params['group_id'])

    def save(self,params):
        self.keys(params,'group_id name description definition expected_revision')
        definition=self.definition(params['definition']);name=self.text(params['name'],128,True);description=self.text(params['description'],512)
        def write():
            state=self.state();identifier=params['group_id'];before=self.item(state,identifier) if identifier is not None else None
            self.revision(params['expected_revision'],before['revision'] if before else 0)
            if not before and len(state['groups'])>=32:raise LibraryError('CATALOG_LIMIT')
            identifier=identifier or str(uuid4())
            after=dict(id=identifier,name=name,description=description,definition=definition,revision=(before['revision'] if before else 0)+1)
            state['groups'][identifier]=after;self.graph(state['groups']);state['revision']+=1
            self.references(criteria(definition['criteria']))
            self.db.execute("INSERT INTO settings VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",(KEY,json.dumps(state,ensure_ascii=False)))
            self.log('smart_group',identifier,after['revision'],'save',before,after);return after
        return self.transaction(write)

    def delete(self,params):
        self.keys(params,'group_id expected_revision')
        def write():
            state=self.state();before=self.item(state,params['group_id']);self.revision(params['expected_revision'],before['revision'])
            if any(before['id'] in r['definition']['include_groups'] for r in state['groups'].values()):raise LibraryError('INVALID_PARAMS')
            del state['groups'][before['id']];state['revision']+=1
            self.db.execute("UPDATE settings SET value_json=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE key=?",(json.dumps(state,ensure_ascii=False),KEY))
            self.log('smart_group',before['id'],before['revision']+1,'delete',before,None);return dict(deleted=True)
        return self.transaction(write)

    def evaluate(self,params):
        self.keys(params,'group_id query criteria sort after_id')
        f=criteria(params['criteria']);sort=params['sort'];query=params['query'];cursor=params['after_id']
        if not isinstance(query,str) or len(query)>256 or len(query.split())>16 or not isinstance(sort,str) or sort not in SORTS:raise LibraryError('INVALID_PARAMS')
        catalog=CatalogQuery(self.database);stamp=catalog.stamp();state=self.state();self.item(state,params['group_id'])
        # Only evaluate the requested group and its transitive dependencies.
        selected={}
        def gather(identifier):
            if identifier in selected:return
            row=self.item(state,identifier);selected[identifier]=row
            for ref in row['definition']['include_groups']:gather(ref)
        gather(params['group_id']);order=self.graph(selected)
        rows=self.db.execute('SELECT d.asset_id,d.searchable_text FROM catalog_documents d JOIN assets a ON a.id=d.asset_id JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 ORDER BY d.asset_id LIMIT 10001').fetchall()
        if len(rows)>10000 or len(rows)*len(order)>50000:raise LibraryError('CATALOG_LIMIT')
        results={}
        for identifier in order:
            definition=self.definition(selected[identifier]['definition']);filters=criteria(definition['criteria']);terms=normalized(definition['query']).split()
            candidates={i for i,text in rows if all(t in text for t in terms) and catalog.matches(i,filters)}
            for ref in definition['include_groups']:candidates &= results[ref]
            results[identifier]=candidates
        terms=normalized(query).split();ids=catalog.sorted_ids([i for i,text in rows if i in results[params['group_id']] and all(t in text for t in terms) and catalog.matches(i,f)],sort,dict(rows),terms)
        digest=hashlib.sha256(json.dumps([params['group_id'],query,f,sort,state['revision']],sort_keys=True).encode()).hexdigest()
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or len(cursor)>512:raise ValueError()
                decoded=json.loads(base64.b64decode(cursor.encode(),altchars=b'-_',validate=True))
                if set(decoded)!={'id','stamp','digest'}:raise ValueError()
                if decoded['stamp']!=stamp or decoded['digest']!=digest or decoded['id'] not in ids:raise LibraryError('METADATA_CONFLICT')
                ids=ids[ids.index(decoded['id'])+1:]
            except (ValueError,TypeError,UnicodeError):raise LibraryError('INVALID_PARAMS') from None
        if catalog.stamp()!=stamp:raise LibraryError('METADATA_CONFLICT')
        next_cursor=base64.urlsafe_b64encode(json.dumps(dict(id=ids[199],stamp=stamp,digest=digest)).encode()).decode() if len(ids)>200 else None
        return dict(ids=ids[:200],next_cursor=next_cursor,inferenceCalled=False)
