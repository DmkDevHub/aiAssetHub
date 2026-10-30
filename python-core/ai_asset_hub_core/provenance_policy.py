"""Explicit private access, bounded read projections, immutable history and reviewed tombstones."""
import json
from .provenance import Provenance
from .creators import Creators
from .collections import Collections
from .source_records import Sources, private_access
from .license_records import Licenses
from .libraries import LibraryError, valid_id


class ProvenancePolicy(Provenance):
    def delete_creator_preview(self, params):
        Collections.keys(params, 'creator_id')
        creator = self.creator(params['creator_id'])
        asset = self.db.execute('SELECT count(*) FROM asset_creator_links WHERE creator_id=?', (creator['id'],)).fetchone()[0]
        package = self.db.execute('SELECT count(*) FROM package_creator_links WHERE creator_id=?', (creator['id'],)).fetchone()[0]
        return dict(creator_id=creator['id'], revision=creator['revision'], assetLinks=asset, packageLinks=package,
                    canDelete=not creator['deleted'] and asset + package == 0)

    def delete_creator(self, params):
        Collections.keys(params, 'plan confirmed')
        if params['confirmed'] is not True: raise LibraryError('INVALID_PARAMS')
        plan = params['plan']; Collections.keys(plan, 'creator_id revision assetLinks packageLinks canDelete')
        if type(plan['canDelete']) is not bool or any(type(plan[key]) is not int or plan[key] < 0 for key in ('revision', 'assetLinks', 'packageLinks')):
            raise LibraryError('INVALID_PARAMS')
        def operation():
            current = self.delete_creator_preview({'creator_id': plan['creator_id']})
            if plan != current: raise LibraryError('METADATA_CONFLICT')
            if not current['canDelete']: raise LibraryError('INVALID_PARAMS')
            before = self.creator(plan['creator_id'])
            self.db.execute('UPDATE creators SET enabled=0,deleted=1,revision=revision+1 WHERE id=?', (before['id'],))
            result = self.creator(before['id'])
            self.audit(result, 'delete', ['enabled', 'deleted'], before)
            return self.public(result)
        return self.write(operation)

    def history_subject(self, subject):
        if isinstance(subject, dict) and subject.get('kind') == 'creator':
            Collections.keys(subject, 'kind id'); self.creator(subject['id'])
        else:
            self.subject(subject, active=False)

    def snapshot(self, value, field, private):
        if value is None: return None
        if not private:
            if field == 'creator': value = self.public(value)
            elif field == 'source': value = Sources(self.database).project(value)
            elif field == 'license': value = Licenses(self.database).project(value)
            elif field != 'creator_links': value = None
        text = json.dumps(value, ensure_ascii=False)
        size = len(text.encode('utf-8'))
        return {'value': value, 'truncated': False} if size <= 4000 else {'value': None, 'truncated': True, 'byteLength': size, 'preview': text[:256]}

    def history(self, params):
        private = private_access(params, {'subject', 'after_id'})
        subject = params['subject']; self.history_subject(subject)
        cursor = params['after_id']; values = [subject['kind'], subject['id']]; condition = ''
        if cursor is not None:
            if not valid_id(cursor): raise LibraryError('INVALID_PARAMS')
            row = self.db.execute('SELECT rowid FROM provenance_history WHERE id=? AND subject_kind=? AND subject_id=?', (cursor, *values)).fetchone()
            if row is None: raise LibraryError('INVALID_PARAMS')
            condition = 'AND rowid<?'; values.append(row[0])
        rows = self.db.execute('SELECT id,entity_id,field,revision,action,before_json,after_json,created_at FROM provenance_history '
                               f'WHERE subject_kind=? AND subject_id=? {condition} ORDER BY rowid DESC LIMIT 2', values).fetchall()
        items = [dict(id=r[0], entityId=r[1], field=r[2], revision=r[3], action=r[4], actor='user',
                      before=self.snapshot(json.loads(r[5]), r[2], private), after=self.snapshot(json.loads(r[6]), r[2], private), createdAt=r[7]) for r in rows[:1]]
        return dict(items=items, next_cursor=items[0]['id'] if len(rows) > 1 else None, privateFieldsExcluded=not private)

    def export(self, params):
        private = private_access(params, {'subject', 'kind', 'after_id'})
        self.subject(params['subject']); kind = params['kind']; cursor = params['after_id']
        if kind == 'creators':
            links = self.links_value(params['subject'])['links']; identifiers = sorted({i['creator_id'] for i in links})
            if cursor is not None and cursor not in identifiers: raise LibraryError('INVALID_PARAMS')
            remaining = [i for i in identifiers if i > (cursor or '')]; items = []
            for identifier in remaining[:1]:
                creator = self.creator(identifier)
                items.append({**(creator if private else self.public(creator)), 'roles': [i['role'] for i in links if i['creator_id'] == identifier]})
            next_cursor = remaining[0] if len(remaining) > 1 else None
        elif kind in ('sources', 'licenses'):
            service = Sources(self.database) if kind == 'sources' else Licenses(self.database)
            page = service.list_records(dict(subject=params['subject'], after_id=cursor))
            items = [service.project(service.record(i['id']), private) for i in page['items'][:1]]
            next_cursor = items[0]['id'] if len(page['items']) > 1 or page['next_cursor'] else None
        else: raise LibraryError('INVALID_PARAMS')
        return dict(schemaVersion=1, kind=kind, items=items, next_cursor=next_cursor, privateFieldsExcluded=not private)
