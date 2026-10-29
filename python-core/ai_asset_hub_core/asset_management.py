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
        elif kind in ('asset', 'incoming'):
            extra = '' if kind == 'asset' else ''' AND EXISTS (SELECT 1 FROM metadata_decisions d,json_each(d.value_json) j
                WHERE d.asset_id=a.id AND d.field='relations' AND json_extract(j.value,'$.targetId')=?)'''
            args = [after or '', params['asset_id']]
            if kind == 'incoming': args.append(params['asset_id'])
            rows = self.db.execute('''SELECT a.id,coalesce(u.title_override,a.display_name) FROM assets a
                JOIN library_roots l ON l.id=a.library_root_id LEFT JOIN asset_user_annotations u ON u.asset_id=a.id
                WHERE l.enabled=1 AND a.id>? AND a.id!=?''' + extra + ' ORDER BY a.id LIMIT 3', args).fetchall()
            items = [{'id': r[0], 'name': r[1][-160:], 'available': True,
                      'relations': [link['kind'] for link in self.relation_value(r[0]) if link['targetId'] == params['asset_id']] if kind == 'incoming' else []} for r in rows[:2]]
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
            # Recheck mutable evidence under the same write lock as the decision.
            for file_id, _ in pairs:
                if not self.file(file_id): raise LibraryError('INVALID_PARAMS')
            for identifier in components:
                row = self.db.execute('SELECT file_id,input_fingerprint FROM asset_components WHERE id=?', (identifier,)).fetchone()
                file = self.file(row[0]) if row else None
                if not file or not file[2] or file[3] != row[1]: raise LibraryError('INVALID_PARAMS')
            self.db.execute('DELETE FROM asset_file_members WHERE asset_id=?', (params['asset_id'],))
            self.db.executemany('INSERT INTO asset_file_members VALUES (?,?,?)', [(params['asset_id'], f, r) for f, r in sorted(pairs)])
        return self.commit(params, 'composition', value, self.composition, project)

    def relation_value(self, asset):
        row = self.db.execute("SELECT value_json FROM metadata_decisions WHERE asset_id=? AND field='relations'", (asset,)).fetchone()
        return json.loads(row[0]) if row else []

    def relations(self, params):
        self.get(params)
        state = self.metadata.effective(params['asset_id'], 'relations')
        links = self.relation_value(params['asset_id'])
        details = []
        for link in links:
            row = self.db.execute('''SELECT coalesce(u.title_override,a.display_name),l.enabled FROM assets a
                JOIN library_roots l ON l.id=a.library_root_id LEFT JOIN asset_user_annotations u ON u.asset_id=a.id WHERE a.id=?''', (link['targetId'],)).fetchone()
            details.append({**link, 'name': row[0][-160:] if row else '사용 불가', 'available': bool(row and row[1])})
        return {'value': links, 'revision': state['revision'], 'items': details}

    def save_relations(self, params):
        self.validate_request(params)
        links = params['value']
        if not isinstance(links, list) or len(links) > 16: raise LibraryError('INVALID_PARAMS')
        seen = set()
        for link in links:
            if not isinstance(link, dict) or set(link) != {'targetId', 'kind'} or not valid_id(link['targetId']) or link['kind'] not in ('related', 'original_of', 'variant_of', 'derived_from') or link['targetId'] == params['asset_id']:
                raise LibraryError('INVALID_PARAMS')
            pair = (link['targetId'], link['kind'])
            if pair in seen: raise LibraryError('INVALID_PARAMS')
            seen.add(pair)

        def validate_graph():
            # Runs under BEGIN IMMEDIATE, including changes on other assets.
            for target, _ in seen: self.require_asset(target)
            graph = {}
            for asset, value in self.db.execute("SELECT asset_id,value_json FROM metadata_decisions WHERE field='relations'"):
                for link in json.loads(value):
                    parent, child = link['targetId'], asset
                    if link['kind'] == 'related': continue
                    if link['kind'] == 'original_of': parent, child = child, parent
                    graph.setdefault(child, set()).add(parent)
            # Kahn traversal avoids recursion limits on long legitimate ancestry chains.
            nodes = set(graph) | {p for parents in graph.values() for p in parents}
            degree = {node: 0 for node in nodes}
            for parents in graph.values():
                for parent in parents: degree[parent] += 1
            pending = [node for node in nodes if degree[node] == 0]
            count = 0
            while pending:
                node = pending.pop(); count += 1
                for parent in graph.get(node, ()):
                    degree[parent] -= 1
                    if degree[parent] == 0: pending.append(parent)
            if count != len(nodes): raise LibraryError('INVALID_PARAMS')

        return self.commit(params, 'relations', links, self.relations, validate_graph)

    def history(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id', 'before_id'}: raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        before = params['before_id']
        if before is not None and (type(before) is not int or before < 1 or not self.db.execute(
                'SELECT 1 FROM metadata_decision_history WHERE id=? AND asset_id=?', (before, params['asset_id'])).fetchone()):
            raise LibraryError('INVALID_PARAMS')
        rows = self.db.execute('''SELECT id,field,revision,action,before_json,after_json,created_at
            FROM metadata_decision_history WHERE asset_id=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT 2''',
                               (params['asset_id'], before, before)).fetchall()

        def bounded(raw):
            value = json.loads(raw) if raw else None
            if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) <= 6000: return value
            preview = raw[:2000]
            while len(json.dumps({'truncated': True, 'preview': preview}, ensure_ascii=False).encode('utf-8')) > 6000:
                preview = preview[:len(preview)//2]
            return {'truncated': True, 'preview': preview}

        return {'items': [{'id': r[0], 'field': r[1], 'revision': r[2], 'action': r[3],
                           'before': bounded(r[4]), 'after': bounded(r[5]), 'createdAt': r[6], 'actor': 'user'} for r in rows[:1]],
                'next_cursor': rows[0][0] if len(rows) > 1 else None}
