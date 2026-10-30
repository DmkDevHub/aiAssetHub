"""Shared creator dictionary. Explicit local writes only; URLs are never fetched."""
import ipaddress
import json
import re
from urllib.parse import urlsplit
from uuid import uuid4
from .collections import Collections
from .libraries import LibraryError, valid_id


FIELDS = ('name', 'kind', 'brand', 'homepageUrl', 'profileUrl', 'contact', 'country', 'description')
COLUMNS = 'id,name,kind,brand,homepage_url,profile_url,contact,country,description,enabled,revision,deleted'


class Creators:
    def __init__(self, database):
        self.db = database.connection
        self.database = database

    @staticmethod
    def url(value):
        text = Collections.text(value, 512)
        if not text:
            return text
        try:
            parts = urlsplit(text)
            if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
                    or parts.password is not None or parts.query or parts.fragment
                    or '?' in text or '#' in text or '\\' in text or any(c.isspace() for c in text)):
                raise ValueError()
            parts.port
            host = parts.hostname
            if ':' in host:
                ipaddress.IPv6Address(host)
            else:
                host = host.encode('idna').decode('ascii').rstrip('.')
                if len(host) > 253 or any(not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label) for label in host.split('.')):
                    raise ValueError()
        except (ValueError, UnicodeError):
            raise LibraryError('INVALID_PARAMS') from None
        return text

    def value(self, value):
        Collections.keys(value, ' '.join(FIELDS))
        if not isinstance(value['kind'], str) or value['kind'] not in ('person', 'team', 'company'):
            raise LibraryError('INVALID_PARAMS')
        return dict(name=Collections.text(value['name'], 128, True), kind=value['kind'],
                    brand=Collections.text(value['brand'], 128), homepageUrl=self.url(value['homepageUrl']),
                    profileUrl=self.url(value['profileUrl']), contact=Collections.text(value['contact'], 256),
                    country=Collections.text(value['country'], 64), description=Collections.text(value['description'], 512))

    def creator(self, identifier):
        if not valid_id(identifier):
            raise LibraryError('INVALID_PARAMS')
        row = self.db.execute(f'SELECT {COLUMNS} FROM creators WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise LibraryError('INVALID_PARAMS')
        result = dict(zip(('id', *FIELDS, 'enabled', 'revision', 'deleted'), row))
        result['enabled'] = bool(result['enabled'])
        result['deleted'] = bool(result['deleted'])
        return result

    @staticmethod
    def public(result):
        return {**{key: result[key] for key in ('id', 'name', 'kind', 'brand', 'country', 'enabled', 'revision')},
                'deleted': result.get('deleted', False), 'privateFieldsExcluded': True}

    def get(self, params):
        from .source_records import private_access
        include = private_access(params, {'creator_id'})
        result = self.creator(params['creator_id'])
        return result if include else self.public(result)

    def list(self, params):
        Collections.keys(params, 'after_id include_disabled')
        if type(params['include_disabled']) is not bool:
            raise LibraryError('INVALID_PARAMS')
        cursor = params['after_id']
        if cursor is not None:
            self.creator(cursor)
        rows = self.db.execute('SELECT id,name,kind,brand,country,enabled,revision FROM creators '
                               'WHERE deleted=0 AND id>? AND (enabled=1 OR ?) ORDER BY id LIMIT 3',
                               (cursor or '', params['include_disabled'])).fetchall()
        items = [dict(zip(('id', 'name', 'kind', 'brand', 'country', 'enabled', 'revision'), row)) for row in rows[:2]]
        for item in items:
            item['enabled'] = bool(item['enabled'])
        return {'items': items, 'next_cursor': items[-1]['id'] if len(rows) > 2 else None}

    def write(self, operation):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = operation()
            self.db.execute('COMMIT')
            return result
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def audit(self, result, action, fields, before=None):
        # Never copy contact, URLs, names, descriptions or other submitted values to logs.
        detail = json.dumps({'revision': result['revision'], 'fields': fields})
        self.db.execute("INSERT INTO audit_events VALUES (?, 'user', ?, 'creator', ?, 'succeeded', strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?)",
                        (str(uuid4()), 'creator.' + action, result['id'], detail))
        from .provenance import Provenance
        Provenance(self.database).event({'kind': 'creator', 'id': result['id']}, result['id'], 'creator', result['revision'], action, before, result, audit=False)

    def create(self, params):
        Collections.keys(params, 'value')
        value = self.value(params['value'])
        def operation():
            identifier = str(uuid4())
            self.db.execute(f'INSERT INTO creators ({COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,1,1,0)',
                            (identifier, *(value[field] for field in FIELDS)))
            result = self.creator(identifier)
            self.audit(result, 'create', list(FIELDS))
            return result
        return self.write(operation)

    def update(self, params):
        Collections.keys(params, 'creator_id value expected_revision')
        value = self.value(params['value'])
        def operation():
            before = self.creator(params['creator_id'])
            if before['deleted']: raise LibraryError('INVALID_PARAMS')
            Collections.revision(params['expected_revision'], before['revision'])
            self.db.execute('UPDATE creators SET name=?,kind=?,brand=?,homepage_url=?,profile_url=?,contact=?,country=?,description=?,revision=revision+1 WHERE id=?',
                            (*(value[field] for field in FIELDS), before['id']))
            result = self.creator(before['id'])
            self.audit(result, 'update', [field for field in FIELDS if before[field] != result[field]], before)
            return result
        return self.write(operation)

    def set_enabled(self, params):
        Collections.keys(params, 'creator_id enabled expected_revision')
        if type(params['enabled']) is not bool:
            raise LibraryError('INVALID_PARAMS')
        def operation():
            before = self.creator(params['creator_id'])
            if before['deleted']: raise LibraryError('INVALID_PARAMS')
            Collections.revision(params['expected_revision'], before['revision'])
            if before['enabled'] == params['enabled']:
                return before
            self.db.execute('UPDATE creators SET enabled=?,revision=revision+1 WHERE id=?', (params['enabled'], before['id']))
            result = self.creator(before['id'])
            self.audit(result, 'set_enabled', ['enabled'], before)
            return result
        return self.write(operation)
