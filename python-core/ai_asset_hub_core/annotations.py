"""User metadata only: never changes source files or analysis history."""
import unicodedata
from uuid import uuid4
from .libraries import LibraryError, valid_id


class AnnotationService:
    def __init__(self, database):
        self.db = database.connection

    def require_asset(self, identifier):
        if not valid_id(identifier) or not self.db.execute('''SELECT 1 FROM assets a
            JOIN library_roots l ON l.id=a.library_root_id WHERE a.id=? AND l.enabled=1''', (identifier,)).fetchone():
            raise LibraryError('INVALID_PARAMS')

    def get(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        tags = [row[0] for row in self.db.execute('''SELECT t.label FROM tags t JOIN asset_tags at ON at.tag_id=t.id
            WHERE at.asset_id=? AND at.source='user' ORDER BY t.normalized_label''', (params['asset_id'],))]
        row = self.db.execute('SELECT title_override,description_override FROM asset_user_annotations WHERE asset_id=?', (params['asset_id'],)).fetchone()
        return {'tags': tags, 'title': row[0] or '' if row else '', 'description': row[1] or '' if row else ''}

    def save(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id', 'title', 'description'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        for key, limit in (('title',128), ('description',1024)):
            value = params[key]
            if not isinstance(value,str) or len(value) > limit or any(unicodedata.category(c).startswith('C') and c not in '\n\t' for c in value):
                raise LibraryError('INVALID_PARAMS')
        self.db.execute('''INSERT INTO asset_user_annotations(asset_id,title_override,description_override,updated_at)
            VALUES (?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(asset_id) DO UPDATE SET
            title_override=excluded.title_override,description_override=excluded.description_override,updated_at=excluded.updated_at''',
            (params['asset_id'],params['title'].strip() or None,params['description'].strip() or None))
        return self.get({'asset_id': params['asset_id']})

    @staticmethod
    def labels(value):
        if not isinstance(value, list) or len(value) > 32:
            raise LibraryError('INVALID_PARAMS')
        result = {}
        for label in value:
            if not isinstance(label, str): raise LibraryError('INVALID_PARAMS')
            label = unicodedata.normalize('NFKC', label).strip()
            if not label or len(label) > 64 or any(unicodedata.category(c).startswith('C') for c in label):
                raise LibraryError('INVALID_PARAMS')
            result[label.casefold()] = label
        return result

    def tags(self, params):
        if not isinstance(params, dict) or set(params) != {'asset_id', 'add', 'remove'}:
            raise LibraryError('INVALID_PARAMS')
        self.require_asset(params['asset_id'])
        add, remove = self.labels(params['add']), self.labels(params['remove'])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for normalized in remove:
                self.db.execute("DELETE FROM asset_tags WHERE asset_id=? AND source='user' AND tag_id IN (SELECT id FROM tags WHERE normalized_label=?)", (params['asset_id'], normalized))
            for normalized, label in add.items():
                self.db.execute('INSERT OR IGNORE INTO tags(id,label,normalized_label) VALUES (?,?,?)', (str(uuid4()), label, normalized))
                self.db.execute("INSERT OR IGNORE INTO asset_tags(asset_id,tag_id,source) SELECT ?,id,'user' FROM tags WHERE normalized_label=?", (params['asset_id'], normalized))
            if self.db.execute("SELECT count(*) FROM asset_tags WHERE asset_id=? AND source='user'", (params['asset_id'],)).fetchone()[0] > 32:
                raise LibraryError('INVALID_PARAMS')
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        return self.get({'asset_id': params['asset_id']})
