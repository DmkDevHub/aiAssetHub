"""User-declared source/purchase records. Network access and downloads are never performed."""
from datetime import date
from decimal import Decimal
import json
import re
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from .collections import Collections
from .creators import Creators
from .provenance import Provenance
from .libraries import LibraryError, valid_id


def private_access(params, required):
    if not isinstance(params, dict) or set(required) - set(params) or set(params) - set(required) - {'include_private', 'confirmed'}:
        raise LibraryError('INVALID_PARAMS')
    include, confirmed = params.get('include_private', False), params.get('confirmed', False)
    if type(include) is not bool or type(confirmed) is not bool or include and not confirmed:
        raise LibraryError('INVALID_PARAMS')
    return include


def source_url(value):
    text = Collections.text(value, 512)
    if not text: return text
    try:
        parts = urlsplit(text)
        Creators.url(urlunsplit((parts.scheme, parts.netloc, parts.path, '', '')))
        if '\\' in text or any(c.isspace() for c in text): raise ValueError()
    except (ValueError, UnicodeError):
        raise LibraryError('INVALID_PARAMS') from None
    return text


class OwnedRecords(Provenance):
    table = 'provenance_sources'
    field = 'source'
    confirmation = False

    def record(self, identifier):
        if not valid_id(identifier): raise LibraryError('INVALID_PARAMS')
        row = self.db.execute(f'SELECT id,asset_id,package_id,value_json,revision,enabled FROM {self.table} WHERE id=?', (identifier,)).fetchone()
        if row is None: raise LibraryError('INVALID_PARAMS')
        return dict(id=row[0], subject={'kind': 'asset' if row[1] else 'package', 'id': row[1] or row[2]},
                    value=json.loads(row[3]), revision=row[4], enabled=bool(row[5]))

    def project(self, record, private=False):
        return {**record, 'value': record['value'] if private else self.public_value(record['value']), 'privateFieldsExcluded': not private}

    def get_record(self, params):
        include = private_access(params, {'record_id'})
        return self.project(self.record(params['record_id']), include)

    def list_records(self, params):
        Collections.keys(params, 'subject after_id')
        kind, identifier = self.subject(params['subject'])
        cursor = params['after_id']
        if cursor is not None and self.record(cursor)['subject'] != params['subject']: raise LibraryError('INVALID_PARAMS')
        column = 'asset_id' if kind == 'asset' else 'package_id'
        rows = self.db.execute(f'SELECT id FROM {self.table} WHERE {column}=? AND enabled=1 AND id>? ORDER BY id LIMIT 3', (identifier, cursor or '')).fetchall()
        return {'items': [self.project(self.record(r[0])) for r in rows[:2]], 'next_cursor': rows[1][0] if len(rows) > 2 else None}

    def check_write(self, params, keys):
        Collections.keys(params, keys + (' confirmed' if self.confirmation else ''))
        if self.confirmation and params['confirmed'] is not True: raise LibraryError('INVALID_PARAMS')

    def create_record(self, params):
        self.check_write(params, 'subject value')
        value = self.value(params['value'])
        def operation():
            kind, owner = self.subject(params['subject']); identifier = str(uuid4())
            self.db.execute(f'INSERT INTO {self.table} VALUES (?,?,?,?,1,1)',
                            (identifier, owner if kind == 'asset' else None, owner if kind == 'package' else None, json.dumps(value, ensure_ascii=False)))
            result = self.record(identifier)
            self.event(params['subject'], identifier, self.field, 1, 'create', None, result)
            return self.project(result)
        return self.write(operation)

    def update_record(self, params):
        self.check_write(params, 'record_id value expected_revision')
        value = self.value(params['value'])
        def operation():
            before = self.record(params['record_id']); self.subject(before['subject'])
            if not before['enabled']: raise LibraryError('INVALID_PARAMS')
            Collections.revision(params['expected_revision'], before['revision'])
            self.db.execute(f'UPDATE {self.table} SET value_json=?,revision=revision+1 WHERE id=?', (json.dumps(value, ensure_ascii=False), before['id']))
            result = self.record(before['id'])
            self.event(before['subject'], before['id'], self.field, result['revision'], 'update', before, result)
            return self.project(result)
        return self.write(operation)

    def delete_record(self, params):
        Collections.keys(params, 'record_id expected_revision confirmed')
        if params['confirmed'] is not True: raise LibraryError('INVALID_PARAMS')
        def operation():
            before = self.record(params['record_id'])
            Collections.revision(params['expected_revision'], before['revision'])
            if not before['enabled']: raise LibraryError('INVALID_PARAMS')
            self.db.execute(f'UPDATE {self.table} SET enabled=0,revision=revision+1 WHERE id=?', (before['id'],))
            result = self.record(before['id'])
            self.event(before['subject'], before['id'], self.field, result['revision'], 'delete', before, result)
            return self.project(result)
        return self.write(operation)


class Sources(OwnedRecords):
    @staticmethod
    def public_value(value):
        return {key: value[key] for key in ('site', 'productName')}

    def project(self, record, private=False):
        result = super().project(record, private)
        if private:
            amount = record['value']['purchase']['amount']
            result['priceState'] = 'unknown' if amount is None else 'free' if Decimal(amount) == 0 else 'paid'
        return result

    def value(self, value):
        Collections.keys(value, 'site productName originalUrl productUrl downloadUrl purchase')
        purchase = value['purchase']; Collections.keys(purchase, 'amount currency purchasedOn downloadedOn')
        amount, currency = purchase['amount'], purchase['currency']
        if amount is not None and (not isinstance(amount, str) or not re.fullmatch(r'(0|[1-9][0-9]{0,11})(\.[0-9]{1,4})?', amount)): raise LibraryError('INVALID_PARAMS')
        if not isinstance(currency, str) or currency and not re.fullmatch('[A-Z]{3}', currency) or amount is not None and not currency: raise LibraryError('INVALID_PARAMS')
        for key in ('purchasedOn', 'downloadedOn'):
            day = purchase[key]
            if not isinstance(day, str): raise LibraryError('INVALID_PARAMS')
            if day:
                try:
                    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', day): raise ValueError()
                    date.fromisoformat(day)
                except ValueError: raise LibraryError('INVALID_PARAMS') from None
        return dict(site=Collections.text(value['site'], 128), productName=Collections.text(value['productName'], 256),
                    originalUrl=source_url(value['originalUrl']), productUrl=source_url(value['productUrl']),
                    downloadUrl=source_url(value['downloadUrl']), purchase=dict(purchase))
