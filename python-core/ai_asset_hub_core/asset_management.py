"""Explicit user metadata commands; no source writes or analysis scheduling."""
from datetime import date
import json
import re
import unicodedata
from .annotations import AnnotationService
from .libraries import LibraryError, valid_id
from .metadata_values import MetadataError


class AssetManagement(AnnotationService):
    @staticmethod
    def text(value, limit):
        if not isinstance(value, str) or len(value) > limit or any(
                unicodedata.category(c).startswith('C') and c not in '\n\t' for c in value):
            raise LibraryError('INVALID_PARAMS')
        return value.strip()

    def read(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        state = self.metadata.effective(params['asset_id'], 'management')
        default = dict(favorite=False, rating=None, status='unreviewed', notes='', assetVersion='',
                       createdDate='', modifiedDate='')
        return {'value': state['value'] if state['source'] == 'user' else default, 'revision': state['revision']}

    def save_management(self, params):
        self.validate_request(params)
        value = params['value']
        if not isinstance(value, dict) or set(value) != {'favorite', 'rating', 'status', 'notes', 'assetVersion', 'createdDate', 'modifiedDate'}:
            raise LibraryError('INVALID_PARAMS')
        if type(value['favorite']) is not bool or (value['rating'] is not None and (type(value['rating']) is not int or not 1 <= value['rating'] <= 5)):
            raise LibraryError('INVALID_PARAMS')
        if value['status'] not in ('unreviewed', 'reviewing', 'approved', 'archived'):
            raise LibraryError('INVALID_PARAMS')
        value = {**value, 'notes': self.text(value['notes'], 1024), 'assetVersion': self.text(value['assetVersion'], 64)}
        for field in ('createdDate', 'modifiedDate'):
            day = value[field]
            if not isinstance(day, str): raise LibraryError('INVALID_PARAMS')
            if day:
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day): raise ValueError()
                    date.fromisoformat(day)
                except ValueError: raise LibraryError('INVALID_PARAMS') from None
        if value['createdDate'] and value['modifiedDate'] and value['createdDate'] > value['modifiedDate']:
            raise LibraryError('INVALID_PARAMS')
        return self.commit(params, 'management', value, self.read)

    def validate_request(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id', 'value', 'expected_revision'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])

    def commit(self, params, field, value, reader, projection=None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.metadata._decide(params['asset_id'], field, 'set', params['expected_revision'], True, value, None)
            if projection: projection()
            result = reader({'asset_id': params['asset_id']})
            self.db.execute('COMMIT')
            return result
        except MetadataError as error:
            self.db.execute('ROLLBACK')
            raise LibraryError('METADATA_CONFLICT' if str(error) == 'METADATA_CONFLICT' else 'INVALID_PARAMS') from None
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def composition(self, params):
        self.get(params)  # strict active asset validation
        asset = params['asset_id']
        state = self.metadata.effective(asset, 'composition')
        files = [{'fileId': f, 'role': r} for f, r in self.db.execute(
            'SELECT file_id,role FROM asset_file_members WHERE asset_id=? ORDER BY file_id,role', (asset,))]
        components = state['value']['components'] if state['source'] == 'user' else []
        details = []
        available = 0
        for link in files:
            row = self.file(link['fileId'])
            present = bool(row and row[2])
            available += present
            details.append({**link, 'name': row[1][-160:] if row else '사용 불가', 'available': present,
                            'owned': bool(row and row[0] == asset)})
        component_details = []
        for identifier in components:
            row = self.db.execute('SELECT file_id,kind,locator_json,input_fingerprint FROM asset_components WHERE id=?', (identifier,)).fetchone()
            file = self.file(row[0]) if row else None
            component_details.append({'id': identifier, 'kind': row[1] if row else 'unknown',
                                      'stale': not bool(row and file and file[2] and file[3] == row[3])})
        return {'value': {'files': files, 'components': components}, 'revision': state['revision'],
                'files': details, 'components': component_details,
                'availability': 'available' if files and available == len(files) else 'partial' if available else 'missing'}

    def file(self, identifier):
        return self.db.execute('''SELECT f.asset_id,f.relative_path,f.exists_flag,f.sha256 FROM asset_files f
            JOIN assets a ON a.id=f.asset_id JOIN library_roots l ON l.id=a.library_root_id
            WHERE f.id=? AND l.enabled=1''', (identifier,)).fetchone()

    def candidates(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id', 'kind', 'after_id'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        after = params['after_id']
        if after is not None and not valid_id(after): raise LibraryError('INVALID_PARAMS')
        kind = params['kind']
        if kind == 'file':
            rows = self.db.execute('''SELECT f.id,f.relative_path,f.exists_flag FROM asset_files f JOIN assets a ON a.id=f.asset_id
                JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 AND f.id>? ORDER BY f.id LIMIT 3''', (after or '',)).fetchall()
            items = [{'id': r[0], 'name': r[1][-160:], 'available': bool(r[2])} for r in rows[:2]]
        elif kind == 'component':
            rows = self.db.execute('''SELECT c.id,c.kind,f.relative_path,c.file_id,c.input_fingerprint=f.sha256 AND f.exists_flag=1
                FROM asset_components c JOIN asset_files f ON f.id=c.file_id JOIN assets a ON a.id=f.asset_id
                JOIN library_roots l ON l.id=a.library_root_id WHERE l.enabled=1 AND c.id>? ORDER BY c.id LIMIT 3''', (after or '',)).fetchall()
            items = [{'id': r[0], 'name': r[1]+': '+r[2][-160:], 'fileId': r[3], 'available': bool(r[4])} for r in rows[:2]]
        else: raise LibraryError('INVALID_PARAMS')
        return {'items': items, 'next_cursor': rows[1][0] if len(rows) > 2 else None}

    def save_composition(self, params):
        self.validate_request(params)
        value = params['value']
        if not isinstance(value, dict) or set(value) != {'files', 'components'}: raise LibraryError('INVALID_PARAMS')
        files, components = value['files'], value['components']
        if not isinstance(files, list) or not 1 <= len(files) <= 16 or not isinstance(components, list) or len(components) > 16:
            raise LibraryError('INVALID_PARAMS')
        pairs = set()
        for link in files:
            if not isinstance(link, dict) or set(link) != {'fileId', 'role'} or not valid_id(link['fileId']) or link['role'] not in ('source', 'dependency', 'preview', 'evidence') or not self.file(link['fileId']):
                raise LibraryError('INVALID_PARAMS')
            pair = (link['fileId'], link['role'])
            if pair in pairs: raise LibraryError('INVALID_PARAMS')
            pairs.add(pair)
        owners = {row[0] for row in self.db.execute('SELECT id FROM asset_files WHERE asset_id=?', (params['asset_id'],))}
        if any((owner, 'source') not in pairs for owner in owners): raise LibraryError('INVALID_PARAMS')
        seen = set()
        for identifier in components:
            if not valid_id(identifier) or identifier in seen: raise LibraryError('INVALID_PARAMS')
            seen.add(identifier)
            row = self.db.execute('SELECT file_id,input_fingerprint FROM asset_components WHERE id=?', (identifier,)).fetchone()
            file = self.file(row[0]) if row else None
            if not file or not file[2] or file[3] != row[1] or row[0] not in {f for f, _ in pairs}:
                raise LibraryError('INVALID_PARAMS')
        def project():
            self.db.execute('DELETE FROM asset_file_members WHERE asset_id=?', (params['asset_id'],))
            self.db.executemany('INSERT INTO asset_file_members VALUES (?,?,?)', [(params['asset_id'], f, r) for f, r in sorted(pairs)])
        return self.commit(params, 'composition', value, self.composition, project)
