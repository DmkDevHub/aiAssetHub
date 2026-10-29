"""Distribution/purchase units, distinct from folders, groups and A14 file assets."""
from datetime import date
import json
import re
from uuid import uuid4
from .collections import Collections
from .libraries import LibraryError,valid_id


class Packages(Collections):
    def package(self, identifier):
        if not valid_id(identifier):raise LibraryError('INVALID_PARAMS')
        row=self.db.execute('SELECT id,name,description,unit,version,purchase_json,defaults_json,revision FROM asset_packages WHERE id=? AND enabled=1',(identifier,)).fetchone()
        if not row:raise LibraryError('INVALID_PARAMS')
        value=dict(zip(('id','name','description','unit','version','purchase','defaults','revision'),row))
        for key in ('purchase','defaults'):value[key]=json.loads(value[key])
        return value

    def package_list(self, params):
        self.keys(params,'after_id');cursor=params['after_id']
        if cursor is not None and not valid_id(cursor):raise LibraryError('INVALID_PARAMS')
        rows=self.db.execute('SELECT id FROM asset_packages WHERE enabled=1 AND id>? ORDER BY id LIMIT 3',(cursor or '',)).fetchall()
        return {'items':[self.package(r[0]) for r in rows[:2]],'next_cursor':rows[1][0] if len(rows)>2 else None}

    def package_value(self, value):
        self.keys(value,'name description unit version purchase')
        self.keys(value['purchase'],'amount currency date')
        amount,currency,day=(value['purchase'][k] for k in ('amount','currency','date'))
        if value['unit'] not in ('distribution','purchase'):raise LibraryError('INVALID_PARAMS')
        if amount is not None and (not isinstance(amount,str) or not re.fullmatch(r'(0|[1-9][0-9]{0,11})(\.[0-9]{1,4})?',amount)):raise LibraryError('INVALID_PARAMS')
        if not isinstance(currency,str) or (currency and not re.fullmatch('[A-Z]{3}',currency)) or (amount is not None and not currency):raise LibraryError('INVALID_PARAMS')
        if not isinstance(day,str):raise LibraryError('INVALID_PARAMS')
        if day:
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError()
                date.fromisoformat(day)
            except ValueError:raise LibraryError('INVALID_PARAMS') from None
        return {'name':self.text(value['name'],128,True),'description':self.text(value['description'],512),
                'unit':value['unit'],'version':self.text(value['version'],64),'purchase':dict(amount=amount,currency=currency,date=day)}

    def package_create(self, params):
        self.keys(params,'value');value=self.package_value(params['value'])
        def operation():
            identifier=str(uuid4())
            self.db.execute("INSERT INTO asset_packages VALUES (?,?,?,?,?,?,'{}',1,1)",(identifier,value['name'],value['description'],value['unit'],value['version'],json.dumps(value['purchase'])))
            result=self.package(identifier);self.log('package',identifier,1,'create',None,result);return result
        return self.transaction(operation)

    def package_update(self, params):
        self.keys(params,'package_id value expected_revision');value=self.package_value(params['value'])
        def operation():
            before=self.package(params['package_id']);self.revision(params['expected_revision'],before['revision'])
            self.db.execute('UPDATE asset_packages SET name=?,description=?,unit=?,version=?,purchase_json=?,revision=revision+1 WHERE id=?',
                            (value['name'],value['description'],value['unit'],value['version'],json.dumps(value['purchase']),before['id']))
            result=self.package(before['id']);self.log('package',before['id'],result['revision'],'update',before,result);return result
        return self.transaction(operation)

    def package_membership(self, params):
        self.keys(params,'asset_id');self.require_asset(params['asset_id'])
        state=self.membership_value(params['asset_id'],'package');items=[]
        for identifier in state['ids']:
            package=self.package(identifier)
            row=self.db.execute('SELECT record_json,created_at FROM package_purchase_snapshots WHERE package_id=? AND asset_id=?',(identifier,params['asset_id'])).fetchone()
            items.append({'id':identifier,'name':package['name'][:64],'unit':package['unit'],
                          'purchaseSnapshot':json.loads(row[0]) if row else None,'recordedAt':row[1] if row else None})
        return {**state,'items':items}

    def package_assign(self, params):
        self.keys(params,'asset_id package_ids expected_revision');ids=params['package_ids']
        if not isinstance(ids,list) or len(ids)>16 or any(not valid_id(i) for i in ids) or len(set(ids))!=len(ids):raise LibraryError('INVALID_PARAMS')
        def operation():
            self.require_asset(params['asset_id']);packages=[self.package(i) for i in ids]
            before=self.membership_value(params['asset_id'],'package');self.revision(params['expected_revision'],before['revision'])
            self.db.execute('DELETE FROM asset_package_members WHERE asset_id=?',(params['asset_id'],))
            for package in packages:
                self.db.execute('INSERT INTO asset_package_members VALUES (?,?)',(package['id'],params['asset_id']))
                self.db.execute("INSERT OR IGNORE INTO package_purchase_snapshots VALUES (?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                                (package['id'],params['asset_id'],json.dumps({'name':package['name'][:64],'purchase':package['purchase']},ensure_ascii=False)))
            self.member_version(params['asset_id'],'package',before,'assign')
            return self.package_membership({'asset_id':params['asset_id']})
        return self.transaction(operation)

    def package_delete(self, params):
        self.keys(params,'package_id expected_revision')
        def operation():
            before=self.package(params['package_id']);self.revision(params['expected_revision'],before['revision'])
            assets=[r[0] for r in self.db.execute('SELECT asset_id FROM asset_package_members WHERE package_id=?',(before['id'],))]
            snapshots={a:self.membership_value(a,'package') for a in assets}
            self.db.execute('DELETE FROM asset_package_members WHERE package_id=?',(before['id'],))
            self.db.execute('UPDATE asset_packages SET enabled=0,revision=revision+1 WHERE id=?',(before['id'],))
            for asset in assets:self.member_version(asset,'package',snapshots[asset],'package_deleted')
            self.log('package',before['id'],before['revision']+1,'delete',before,None)
            return {'deleted':before['id'],'affectedAssets':len(assets)}
        return self.transaction(operation)
