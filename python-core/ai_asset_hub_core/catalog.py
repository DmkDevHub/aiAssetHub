"""Bounded offline catalog navigation and editing contracts. No model/file actions."""
import json
from .collections import Collections
from .libraries import LibraryError, valid_id


class Catalog(Collections):
    def options(self, params):
        self.keys(params, 'kind after_id')
        kind, cursor = params['kind'], params['after_id']
        if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 128): raise LibraryError('INVALID_PARAMS')
        queries = {
            'groups': 'SELECT id,name,parent_id FROM asset_groups WHERE id>? ORDER BY id LIMIT 21',
            'packages': 'SELECT id,name,NULL FROM asset_packages WHERE enabled=1 AND id>? ORDER BY id LIMIT 21',
            'creators': 'SELECT id,name,NULL FROM creators WHERE enabled=1 AND deleted=0 AND id>? ORDER BY id LIMIT 21',
            'tags': 'SELECT id,label,NULL FROM tags WHERE id>? ORDER BY id LIMIT 21',
            'types': "SELECT code,ko,parent_code FROM classification_terms WHERE version=(SELECT version FROM classification_dictionaries WHERE kind='type' ORDER BY rowid DESC LIMIT 1) AND active=1 AND code>? ORDER BY code LIMIT 21",
        }
        if not isinstance(kind, str) or kind not in queries: raise LibraryError('INVALID_PARAMS')
        rows = self.db.execute(queries[kind], (cursor or '',)).fetchall()
        return {'items': [dict(id=r[0], name=r[1][:64], parentId=r[2]) for r in rows[:20]], 'next_cursor': rows[19][0] if len(rows) > 20 else None}

    def scope(self, params):
        self.keys(params, 'kind id after_id')
        kind, identifier, cursor = params['kind'], params['id'], params['after_id']
        if cursor is not None and not valid_id(cursor): raise LibraryError('INVALID_PARAMS')
        if kind == 'groups':
            self.group(identifier)
            condition = 'EXISTS(SELECT 1 FROM asset_group_members m WHERE m.asset_id=a.id AND m.group_id=?)'; args = [identifier]
        elif kind == 'packages':
            if not valid_id(identifier) or not self.db.execute('SELECT 1 FROM asset_packages WHERE id=? AND enabled=1', (identifier,)).fetchone(): raise LibraryError('INVALID_PARAMS')
            condition = 'EXISTS(SELECT 1 FROM asset_package_members m WHERE m.asset_id=a.id AND m.package_id=?)'; args = [identifier]
        elif kind == 'types':
            if not isinstance(identifier, str) or not self.db.execute("SELECT 1 FROM classification_terms WHERE axis='type' AND code=?", (identifier,)).fetchone(): raise LibraryError('INVALID_PARAMS')
            condition = "(EXISTS(SELECT 1 FROM asset_classification_selections s WHERE s.asset_id=a.id AND (s.primary_code=? OR s.primary_code LIKE ?)) OR EXISTS(SELECT 1 FROM asset_classification_links m WHERE m.asset_id=a.id AND m.axis='type' AND (m.code=? OR m.code LIKE ?)))"
            args = [identifier, identifier + '.%', identifier, identifier + '.%']
        else: raise LibraryError('INVALID_PARAMS')
        rows = self.db.execute('SELECT a.id FROM assets a JOIN library_roots l ON l.id=a.library_root_id '
                               f'WHERE l.enabled=1 AND a.id>? AND {condition} ORDER BY a.id LIMIT 201', (cursor or '', *args)).fetchall()
        ids = [r[0] for r in rows[:200]]
        return {'ids': ids, 'next_cursor': ids[-1] if len(rows) > 200 else None}
