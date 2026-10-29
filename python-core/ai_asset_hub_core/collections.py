"""Logical collections only. All writes are explicit and transactional; no file or AI actions."""
import json
import unicodedata
from uuid import uuid4
from .libraries import LibraryError, valid_id
from .annotations import AnnotationService


class Collections(AnnotationService):
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
        return {**value,'items':[self.group(identifier) for identifier in value['ids']]}

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
