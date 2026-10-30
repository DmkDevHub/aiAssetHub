"""Core-owned authorship/provenance writes. No network or original-file mutations."""
import json
from uuid import uuid4
from .creators import Creators
from .collections import Collections
from .libraries import LibraryError, valid_id


class Provenance(Creators):
    def subject(self, value, active=True):
        Collections.keys(value, 'kind id')
        kind, identifier = value['kind'], value['id']
        if kind not in ('asset', 'package') or not valid_id(identifier):
            raise LibraryError('INVALID_PARAMS')
        if kind == 'asset':
            row = self.db.execute('SELECT l.enabled FROM assets a JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=?', (identifier,)).fetchone()
        else:
            row = self.db.execute('SELECT enabled FROM asset_packages WHERE id=?', (identifier,)).fetchone()
        if row is None or active and not row[0]:
            raise LibraryError('INVALID_PARAMS')
        return kind, identifier

    def event(self, subject, entity, field, revision, action, before, after):
        self.db.execute("INSERT INTO provenance_history VALUES (?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                        (str(uuid4()), subject['kind'], subject['id'], entity, field, revision, action,
                         json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False)))
        # General diagnostics contain identifiers/actions only, never submitted values.
        self.db.execute("INSERT INTO audit_events VALUES (?,'user',?,?,?,'succeeded',strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",
                        (str(uuid4()), field + '.' + action, subject['kind'], subject['id'], json.dumps({'entityId': entity, 'revision': revision})))

    def links_value(self, subject):
        kind, identifier = self.subject(subject)
        table, column, versions = ('asset_creator_links', 'asset_id', 'asset_creator_revisions') if kind == 'asset' else ('package_creator_links', 'package_id', 'package_creator_revisions')
        rows = self.db.execute(f'SELECT creator_id,role FROM {table} WHERE {column}=? ORDER BY creator_id,role', (identifier,)).fetchall()
        revision = self.db.execute(f'SELECT revision FROM {versions} WHERE {column}=?', (identifier,)).fetchone()
        items = []
        for creator_id, role in rows:
            creator = self.creator(creator_id)
            items.append({key: creator[key] for key in ('id', 'name', 'kind', 'brand', 'enabled', 'revision')} | {'role': role})
            for key in ('name', 'brand'):
                items[-1][key] = items[-1][key][:64]
        return {'links': [{'creator_id': r[0], 'role': r[1]} for r in rows], 'items': items, 'revision': revision[0] if revision else 0}

    def links(self, params):
        Collections.keys(params, 'subject')
        return self.links_value(params['subject'])

    def save_links(self, params):
        Collections.keys(params, 'subject links expected_revision')
        links = params['links']
        if not isinstance(links, list) or len(links) > 16:
            raise LibraryError('INVALID_PARAMS')
        pairs = []
        for item in links:
            Collections.keys(item, 'creator_id role')
            if not valid_id(item['creator_id']) or item['role'] not in ('creator', 'producer', 'distributor'):
                raise LibraryError('INVALID_PARAMS')
            pairs.append((item['creator_id'], item['role']))
        if len(set(pairs)) != len(pairs):
            raise LibraryError('INVALID_PARAMS')
        def operation():
            kind, identifier = self.subject(params['subject'])
            before = self.links_value(params['subject'])
            Collections.revision(params['expected_revision'], before['revision'])
            existing = {(i['creator_id'], i['role']) for i in before['links']}
            for creator_id, role in pairs:
                if not self.creator(creator_id)['enabled'] and (creator_id, role) not in existing:
                    raise LibraryError('INVALID_PARAMS')
            table, column, versions = ('asset_creator_links', 'asset_id', 'asset_creator_revisions') if kind == 'asset' else ('package_creator_links', 'package_id', 'package_creator_revisions')
            self.db.execute(f'DELETE FROM {table} WHERE {column}=?', (identifier,))
            self.db.executemany(f'INSERT INTO {table} VALUES (?,?,?)', [(identifier, *p) for p in pairs])
            revision = before['revision'] + 1
            self.db.execute(f'INSERT INTO {versions} VALUES (?,?) ON CONFLICT({column}) DO UPDATE SET revision=excluded.revision', (identifier, revision))
            result = self.links_value(params['subject'])
            self.event(params['subject'], identifier, 'creator_links', revision, 'save', before['links'], result['links'])
            return result
        return self.write(operation)
