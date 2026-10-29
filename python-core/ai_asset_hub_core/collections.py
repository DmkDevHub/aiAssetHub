"""Logical collections only. All writes are explicit and transactional; no file or AI actions."""
import json
import unicodedata
from uuid import uuid4
from .libraries import LibraryError, valid_id
from .annotations import AnnotationService


class Collections(AnnotationService):
    def __init__(self,database):
        super().__init__(database);self.database=database

    @staticmethod
    def keys(params, keys):
        if not isinstance(params, dict) or set(params) != set(keys.split()): raise LibraryError('INVALID_PARAMS')

    @staticmethod
    def text(value, limit, required=False):
        if not isinstance(value, str) or len(value) > limit or any(unicodedata.category(c).startswith('C') for c in value):
            raise LibraryError('INVALID_PARAMS')
        value=unicodedata.normalize('NFKC',value).strip()
        if len(value)>limit or (required and not value): raise LibraryError('INVALID_PARAMS')
        return value

    @staticmethod
    def revision(expected, actual):
        if type(expected) is not int or expected<0: raise LibraryError('INVALID_PARAMS')
        if expected != actual: raise LibraryError('METADATA_CONFLICT')

    def transaction(self, operation):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result=operation();self.db.execute('COMMIT');return result
        except Exception:
            self.db.execute('ROLLBACK');raise

    def log(self,kind,identifier,revision,action,before,after):
        self.db.execute("INSERT INTO collection_history(kind,entity_id,revision,action,before_json,after_json,created_at) VALUES (?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                        (kind,identifier,revision,action,json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))

    def group(self, identifier):
        if not valid_id(identifier): raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT id,name,description,parent_id,revision FROM asset_groups WHERE id=?',(identifier,)).fetchone()
        if not row: raise LibraryError('INVALID_PARAMS')
        return dict(zip(('id','name','description','parentId','revision'),row))

    def group_list(self, params):
        self.keys(params,'after_id')
        cursor=params['after_id']
        if cursor is not None and not valid_id(cursor): raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute('SELECT id FROM asset_groups WHERE id>? ORDER BY id LIMIT 3',(cursor or '',)).fetchall()
        return {'items':[self.group(row[0]) for row in rows[:2]],'next_cursor':rows[1][0] if len(rows)>2 else None}

    def group_value(self, value):
        self.keys(value,'name description')
        return {'name':self.text(value['name'],128,True),'description':self.text(value['description'],512)}

    def group_create(self, params):
        self.keys(params,'value');value=self.group_value(params['value'])
        def operation():
            identifier=str(uuid4())
            self.db.execute('INSERT INTO asset_groups VALUES (?,?,?,NULL,1)',(identifier,value['name'],value['description']))
            result=self.group(identifier);self.log('group',identifier,1,'create',None,result);return result
        return self.transaction(operation)

    def group_update(self, params):
        self.keys(params,'group_id value expected_revision');value=self.group_value(params['value'])
        def operation():
            before=self.group(params['group_id']);self.revision(params['expected_revision'],before['revision'])
            self.db.execute('UPDATE asset_groups SET name=?,description=?,revision=revision+1 WHERE id=?',(value['name'],value['description'],before['id']))
            result=self.group(before['id']);self.log('group',before['id'],result['revision'],'update',before,result);return result
        return self.transaction(operation)

    def membership_value(self, asset, kind='group'):
        table='asset_group_members' if kind=='group' else 'asset_package_members'
        column='group_id' if kind=='group' else 'package_id'
        ids=[r[0] for r in self.db.execute(f'SELECT {column} FROM {table} WHERE asset_id=? ORDER BY {column}',(asset,))]
        row=self.db.execute('SELECT revision FROM asset_collection_versions WHERE asset_id=? AND kind=?',(asset,kind)).fetchone()
        return {'ids':ids,'revision':row[0] if row else 0}

    def member_version(self,asset,kind,before,action):
        current=self.membership_value(asset,kind);revision=before['revision']+1
        self.db.execute('INSERT INTO asset_collection_versions VALUES (?,?,?) ON CONFLICT(asset_id,kind) DO UPDATE SET revision=excluded.revision',(asset,kind,revision))
        current['revision']=revision;self.log(kind+'_members',asset,revision,action,before,current)
        return current

    def group_membership(self, params):
        self.keys(params,'asset_id');self.require_asset(params['asset_id'])
        value=self.membership_value(params['asset_id'])
        return {**value,'items':[{'id':identifier,'name':self.group(identifier)['name'][:64]} for identifier in value['ids']]}

    def group_assign(self, params):
        self.keys(params,'asset_id group_ids expected_revision');ids=params['group_ids']
        if not isinstance(ids,list) or len(ids)>32 or any(not valid_id(i) for i in ids) or len(set(ids))!=len(ids): raise LibraryError('INVALID_PARAMS')
        def operation():
            self.require_asset(params['asset_id'])
            for identifier in ids:self.group(identifier)
            before=self.membership_value(params['asset_id']);self.revision(params['expected_revision'],before['revision'])
            self.db.execute('DELETE FROM asset_group_members WHERE asset_id=?',(params['asset_id'],))
            self.db.executemany('INSERT INTO asset_group_members VALUES (?,?)',[(i,params['asset_id']) for i in ids])
            self.member_version(params['asset_id'],'group',before,'assign')
            return self.group_membership({'asset_id':params['asset_id']})
        return self.transaction(operation)

    def group_delete(self, params):
        self.keys(params,'group_id expected_revision')
        def operation():
            before=self.group(params['group_id']);self.revision(params['expected_revision'],before['revision'])
            members=[r[0] for r in self.db.execute('SELECT asset_id FROM asset_group_members WHERE group_id=?',(before['id'],))]
            snapshots={asset:self.membership_value(asset) for asset in members}
            children=[r[0] for r in self.db.execute('SELECT id FROM asset_groups WHERE parent_id=?',(before['id'],))]
            for child in children:
                old=self.group(child)
                self.db.execute('UPDATE asset_groups SET parent_id=NULL,revision=revision+1 WHERE id=?',(child,))
                self.log('group',child,old['revision']+1,'parent_deleted',old,self.group(child))
            self.db.execute('DELETE FROM asset_groups WHERE id=?',(before['id'],))
            for asset in members:self.member_version(asset,'group',snapshots[asset],'group_deleted')
            self.log('group',before['id'],before['revision']+1,'delete',before,None)
            return {'deleted':before['id'],'affectedAssets':len(members),'promotedChildren':len(children)}
        return self.transaction(operation)

    def group_move(self, params):
        self.keys(params,'group_id parent_id expected_revision')
        if params['parent_id'] is not None and not valid_id(params['parent_id']): raise LibraryError('INVALID_PARAMS')
        def operation():
            before=self.group(params['group_id']);self.revision(params['expected_revision'],before['revision'])
            parent=params['parent_id'];seen={before['id']}
            while parent is not None:
                if parent in seen: raise LibraryError('INVALID_PARAMS')
                seen.add(parent);parent=self.group(parent)['parentId']
            self.db.execute('UPDATE asset_groups SET parent_id=?,revision=revision+1 WHERE id=?',(params['parent_id'],before['id']))
            result=self.group(before['id']);self.log('group',before['id'],result['revision'],'move',before,result);return result
        return self.transaction(operation)

    def group_query(self, params):
        from .semantic_search import criteria,matches
        self.keys(params,'group_id query criteria after_id');self.group(params['group_id'])
        query=params['query'];cursor=params['after_id']
        if not isinstance(query,str) or len(query)>256 or len(query.split())>16 or (cursor is not None and not valid_id(cursor)): raise LibraryError('INVALID_PARAMS')
        filters=criteria(params['criteria']);filters['group_id']=params['group_id']
        terms=unicodedata.normalize('NFKC',query).casefold().split()
        # Evaluate every filter before pagination, including current analysis state and folder segments.
        rows=self.db.execute('''SELECT m.asset_id,d.searchable_text FROM asset_group_members m
            JOIN search_documents d ON d.asset_id=m.asset_id WHERE m.group_id=? AND m.asset_id>? ORDER BY m.asset_id''',(params['group_id'],cursor or ''))
        ids=[]
        for identifier,text in rows:
            if all(term in text for term in terms) and matches(self.database,identifier,filters):
                ids.append(identifier)
                if len(ids)==201:break
        return {'ids':ids[:200],'next_cursor':ids[199] if len(ids)>200 else None}

    def batch_plan(self, asset_ids, add, remove):
        if not isinstance(asset_ids,list) or not 1<=len(asset_ids)<=100 or any(not valid_id(i) for i in asset_ids) or len(set(asset_ids))!=len(asset_ids): raise LibraryError('INVALID_PARAMS')
        for ids in (add,remove):
            if not isinstance(ids,list) or len(ids)>8 or any(not valid_id(i) for i in ids) or len(set(ids))!=len(ids): raise LibraryError('INVALID_PARAMS')
        if not add and not remove or set(add)&set(remove): raise LibraryError('INVALID_PARAMS')
        groups=[self.group(i) for i in sorted(set(add+remove))]
        ids=sorted(asset_ids);targets=[]
        for asset in ids:
            self.require_asset(asset);before=self.membership_value(asset)
            after=sorted((set(before['ids'])-set(remove))|set(add))
            if len(after)>32:raise LibraryError('INVALID_PARAMS')
            targets.append({'assetId':asset,'before':before['ids'],'after':after,'revision':before['revision']})
        return {'assetIds':ids,'add':sorted(add),'remove':sorted(remove),'revisions':[t['revision'] for t in targets],
                'groupVersions':[{ 'id':g['id'],'revision':g['revision']} for g in groups]},targets

    def group_batch_preview(self, params):
        self.keys(params,'asset_ids add remove after_id')
        def operation():
            plan,targets=self.batch_plan(params['asset_ids'],params['add'],params['remove'])
            cursor=params['after_id']
            if cursor is not None and (not valid_id(cursor) or cursor not in plan['assetIds']):raise LibraryError('INVALID_PARAMS')
            rows=[t for t in targets if cursor is None or t['assetId']>cursor]
            return {'plan':plan,'items':rows[:2],'next_cursor':rows[1]['assetId'] if len(rows)>2 else None,'targetCount':len(targets)}
        return self.transaction(operation)

    def group_batch_apply(self, params):
        self.keys(params,'plan confirmed')
        if params['confirmed'] is not True:raise LibraryError('INVALID_PARAMS')
        plan=params['plan'];self.keys(plan,'assetIds add remove revisions groupVersions')
        if not isinstance(plan['revisions'],list) or any(type(r) is not int or r<0 for r in plan['revisions']):raise LibraryError('INVALID_PARAMS')
        def operation():
            current,targets=self.batch_plan(plan['assetIds'],plan['add'],plan['remove'])
            if current != plan:raise LibraryError('METADATA_CONFLICT')
            for target in targets:
                asset=target['assetId'];before=self.membership_value(asset)
                self.db.execute('DELETE FROM asset_group_members WHERE asset_id=?',(asset,))
                self.db.executemany('INSERT INTO asset_group_members VALUES (?,?)',[(i,asset) for i in target['after']])
                self.member_version(asset,'group',before,'batch_assign')
            return {'updated':len(targets)}
        return self.transaction(operation)
